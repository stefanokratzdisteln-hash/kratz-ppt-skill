"""Read-only forensic measurement of the supplied PPTX; no document code executed.

This is a focused OOXML extractor, not a renderer. Character counts include spaces
inside runs, but exclude line/paragraph breaks. Choice content takes precedence over
AlternateContent Fallback. Raster figure labels and master/layout sample text are
not included in editable-text statistics. Positions are unrotated bounding boxes.
"""
from pathlib import Path
from collections import Counter
from io import BytesIO
import argparse, colorsys, hashlib, json, posixpath, re, statistics, zipfile
from lxml import etree as E
from PIL import Image

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path, help='Input .pptx; opened read-only')
parser.add_argument('--output-dir', type=Path, default=Path.cwd()/'kratz-ppt-audit', help='Directory for ooxml_metrics.json and ooxml_findings.md')
args=parser.parse_args(); SOURCE=args.source; OUT=args.output_dir
NS = {'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
      'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
      'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
      'm':'http://schemas.openxmlformats.org/officeDocument/2006/math',
      'mc':'http://schemas.openxmlformats.org/markup-compatibility/2006'}
EMU = 914400
z = zipfile.ZipFile(SOURCE)

def xml(path): return E.fromstring(z.read(path))
def find(el, path): return None if el is None else el.find(path, NS)
def tag(el): return E.QName(el).localname
def rels(path):
    rp = posixpath.join(posixpath.dirname(path), '_rels', posixpath.basename(path)+'.rels')
    if rp not in z.namelist(): return {}
    return {n.get('Id'):{'target':posixpath.normpath(posixpath.join(posixpath.dirname(path),n.get('Target'))),
                         'type':n.get('Type'), 'external':n.get('TargetMode')=='External'} for n in xml(rp)}
def related(path, kind):
    return next((v['target'] for v in rels(path).values() if v['type'].endswith('/'+kind)), None)
def active_children(parent):
    for n in parent:
        if tag(n)=='AlternateContent':
            choice=find(n,'mc:Choice')
            if choice is None: choice=find(n,'mc:Fallback')
            yield from active_children(choice)
        else: yield n
def loc(el): return el.getroottree().getpath(el)
def record_value(el, attr, cast=str):
    return None if el is None or attr not in el.attrib else cast(el.get(attr))

pres=xml('ppt/presentation.xml')
sz=find(pres,'p:sldSz'); W=int(sz.get('cx')); H=int(sz.get('cy')); AREA=W*H
pr=rels('ppt/presentation.xml')
slide_paths=[pr[n.get('{'+NS['r']+'}id')]['target'] for n in find(pres,'p:sldIdLst')]

def color(node, theme, cmap):
    if node is None: return None
    if tag(node) in ('solidFill','fontRef','fillRef','lnRef'):
        node=next((x for x in node if tag(x).endswith('Clr')),None)
    if node is None: return None
    kind=tag(node); raw=dict(node.attrib); transforms=[{'type':tag(x),**dict(x.attrib)} for x in node]
    hexval=None; alpha=1.; unsupported=[]
    if kind=='srgbClr': hexval=node.get('val')
    elif kind=='prstClr':
        # Standard DrawingML preset values occurring in this reference deck.
        hexval={'white':'FFFFFF','black':'000000','red':'FF0000','blue':'0000FF','green':'008000',
                'yellow':'FFFF00','cyan':'00FFFF','magenta':'FF00FF','gray':'808080','silver':'C0C0C0'}.get(node.get('val'))
    elif kind=='sysClr': hexval=node.get('lastClr')
    elif kind=='schemeClr':
        key=cmap.get(node.get('val'),node.get('val'))
        base=find(theme,'a:themeElements/a:clrScheme/a:'+key)
        if base is not None and len(base):
            d=color(base[0],theme,cmap); hexval=d['hex']
    elif kind=='scrgbClr':
        def srgb(v): return 12.92*v if v<=.0031308 else 1.055*v**(1/2.4)-.055
        hexval=''.join(f'{round(255*srgb(int(node.get(k))/100000)):02X}' for k in ('r','g','b'))
    if hexval:
        rgb=tuple(int(hexval[i:i+2],16)/255 for i in (0,2,4))
        for t in node:
            name=tag(t); v=int(t.get('val','0'))/100000
            if name=='alpha': alpha=v
            elif name=='alphaMod': alpha*=v
            elif name=='alphaOff': alpha+=v
            elif name in ('lumMod','lumOff','satMod','satOff','hueMod','hueOff'):
                h,l,s=colorsys.rgb_to_hls(*rgb)
                if name=='lumMod': l*=v
                elif name=='lumOff': l+=v
                elif name=='satMod': s*=v
                elif name=='satOff': s+=v
                elif name=='hueMod': h*=v
                elif name=='hueOff': h+=int(t.get('val'))/21600000
                rgb=colorsys.hls_to_rgb(h%1,max(0,min(1,l)),max(0,min(1,s)))
            elif name=='tint': rgb=tuple(v*c+(1-v) for c in rgb)
            elif name=='shade': rgb=tuple(v*c for c in rgb)
            else: unsupported.append(name)
        hexval=''.join(f'{max(0,min(255,round(v*255))):02X}' for v in rgb)
    return {'hex':hexval,'opacity':round(alpha,5),'raw_kind':kind,'raw':raw,'transforms':transforms,'unsupported_transforms':unsupported}

def theme_font(raw, theme):
    if not raw or not raw.startswith('+'): return raw
    which='majorFont' if raw[1:3]=='mj' else 'minorFont'
    script={'lt':'latin','ea':'ea','cs':'cs'}.get(raw[-2:],'latin')
    n=find(theme,'a:themeElements/a:fontScheme/a:'+which+'/a:'+script)
    return None if n is None else n.get('typeface') or '[script/language dependent]'

def matching_placeholder(root, ph):
    if ph is None: return None
    for s in root.findall('.//p:sp',NS):
        p=find(s,'p:nvSpPr/p:nvPr/p:ph')
        if p is not None and p.get('idx','0')==ph.get('idx','0'): return s
    return None

def bounds(shape, fallbacks=()):
    for source in [shape,*fallbacks]:
        x=find(source,'p:spPr/a:xfrm')
        if x is None: continue
        off=find(x,'a:off'); ext=find(x,'a:ext')
        if off is not None and ext is not None:
            box=[int(off.get('x')),int(off.get('y')),int(ext.get('cx')),int(ext.get('cy'))]
            return {'emu':box,'inches':[round(v/EMU,6) for v in box],
                    'slide_fraction':[round(box[0]/W,6),round(box[1]/H,6),round(box[2]/W,6),round(box[3]/H,6)],
                    'rotation_deg':int(x.get('rot','0'))/60000,'source_xpath':loc(x)}
    return None

def clip(box):
    x,y,w,h=box
    return [max(0,x),max(0,y),max(0,min(W,x+w)-max(0,x)),max(0,min(H,y+h)-max(0,y))]
def area(box): return box[2]*box[3]
def coverage(rects, with_opacity=False):
    """Exact union/alpha composite for axis-aligned rectangles clipped to slide."""
    rr=[(clip(b),a) for b,a in rects if b is not None]
    xs=sorted({q for b,a in rr for q in (b[0],b[0]+b[2])}); ys=sorted({q for b,a in rr for q in (b[1],b[1]+b[3])})
    total=0; by_alpha=Counter()
    for x1,x2 in zip(xs,xs[1:]):
        for y1,y2 in zip(ys,ys[1:]):
            alphas=[a for b,a in rr if b[0]<=(x1+x2)/2<=b[0]+b[2] and b[1]<=(y1+y2)/2<=b[1]+b[3]]
            if not alphas: continue
            a=1.
            for v in alphas: a*=1-v
            a=round(1-a,8); ar=(x2-x1)*(y2-y1); total+=ar; by_alpha[str(a)]+=ar/AREA
    return {'union_slide_fraction':total/AREA,'composited_opacity_area_distribution':dict(sorted(by_alpha.items()))} if with_opacity else total/AREA

all_runs=[]; all_paras=[]; all_objects=[]; slides=[]
for slide_no,path in enumerate(slide_paths,1):
    root=xml(path); layout_path=related(path,'slideLayout'); layout=xml(layout_path)
    master_path=related(layout_path,'slideMaster'); master=xml(master_path)
    theme_path=related(master_path,'theme'); theme=xml(theme_path)
    cmap=dict(find(master,'p:clrMap').attrib)
    for source in (layout,root):
        override=find(source,'p:clrMapOvr/a:overrideClrMapping')
        if override is not None: cmap.update(override.attrib)
    relationships=rels(path); objects=[]
    for order,shape in enumerate(active_children(find(root,'p:cSld/p:spTree'))):
        kind=tag(shape)
        if kind not in ('sp','pic','graphicFrame','grpSp','cxnSp'): continue
        nv=next((n for n in shape.iter() if tag(n)=='cNvPr'),None)
        ph=find(shape,'p:nvSpPr/p:nvPr/p:ph'); layout_shape=matching_placeholder(layout,ph); master_shape=matching_placeholder(master,ph)
        obj={'slide':slide_no,'part':path,'xpath':loc(shape),'id':nv.get('id') if nv is not None else None,
             'name':nv.get('name') if nv is not None else None,'kind':kind,'z_order':order,
             'placeholder':dict(ph.attrib) if ph is not None else None,
             'bounds':bounds(shape,(layout_shape,master_shape))}
        obj['geometry']=record_value(find(shape,'p:spPr/a:prstGeom'),'prst')
        obj['fill']=color(find(shape,'p:spPr/a:solidFill'),theme,cmap)
        obj['fill_is_direct']=obj['fill'] is not None
        obj['line_no_fill']=find(shape,'p:spPr/a:ln/a:noFill') is not None
        if obj['bounds']:
            obj['unclipped_area_slide_fraction']=area(obj['bounds']['emu'])/AREA
            obj['clipped_area_slide_fraction']=area(clip(obj['bounds']['emu']))/AREA
        blip=find(shape,'p:blipFill/a:blip')
        if blip is not None:
            rid=blip.get('{'+NS['r']+'}embed'); target=relationships.get(rid,{}).get('target')
            obj['image']={'relationship_id':rid,'media_part':target}
            crop=find(shape,'p:blipFill/a:srcRect')
            obj['image']['crop_fractions']={k:int(crop.get(k,'0'))/100000 for k in ('l','t','r','b')} if crop is not None else {k:0 for k in ('l','t','r','b')}
            try:
                im=Image.open(BytesIO(z.read(target)))
                obj['image'].update({'pixels':list(im.size),'format':im.format,'sha256':hashlib.sha256(z.read(target)).hexdigest()})
                if obj['bounds']:
                    b=obj['bounds']['emu']; cr=obj['image']['crop_fractions']; visible_ar=im.width*(1-cr['l']-cr['r'])/(im.height*(1-cr['t']-cr['b']))
                    obj['image']['display_aspect_to_visible_source_ratio']=(b[2]/b[3])/visible_ar
                    obj['image']['effective_horizontal_ppi']=im.width*(1-cr['l']-cr['r'])/(b[2]/EMU)
            except Exception as e: obj['image']['inspection_error']=str(e)
            obj['background_candidate']=obj.get('clipped_area_slide_fraction',0)>=.85
        tb=find(shape,'p:txBody'); obj['paragraphs']=[]; obj['runs']=[]
        if tb is not None:
            bp=find(tb,'a:bodyPr'); obj['body_properties']=dict(bp.attrib) if bp is not None else {}
            obj['autofit']=[tag(x) for x in bp if tag(x).endswith('Autofit') or tag(x).endswith('AutoFit')] if bp is not None else []
            obj['text_margins_emu']={k:int(bp.get(k,v)) for k,v in [('lIns','91440'),('rIns','91440'),('tIns','45720'),('bIns','45720')]} if bp is not None else None
            for pi,p in enumerate(tb.findall('a:p',NS),1):
                pp=find(p,'a:pPr'); level=int(pp.get('lvl','0')) if pp is not None else 0
                phtype=ph.get('type','body') if ph is not None else 'other'
                master_style='titleStyle' if phtype in ('title','ctrTitle') else 'bodyStyle' if phtype=='body' else 'otherStyle'
                sources=[]
                def add(n,label):
                    if n is not None: sources.append((n,label))
                add(pp,'paragraph')
                for label,sh in [('shape',shape),('layout_placeholder',layout_shape),('master_placeholder',master_shape)]:
                    add(find(sh,f'p:txBody/a:lstStyle/a:lvl{level+1}pPr'),label+'_level')
                    add(find(sh,'p:txBody/a:lstStyle/a:defPPr'),label+'_default')
                add(find(master,f'p:txStyles/p:{master_style}/a:lvl{level+1}pPr'),'master_'+master_style+'_level')
                add(find(master,f'p:txStyles/p:{master_style}/a:defPPr'),'master_'+master_style+'_default')
                add(find(pres,f'p:defaultTextStyle/a:lvl{level+1}pPr'),'presentation_default_level')
                add(find(pres,'p:defaultTextStyle/a:defPPr'),'presentation_default')
                def para_attr(key,default=None):
                    for n,label in sources:
                        if key in n.attrib: return n.get(key),label
                    return default,'OOXML_default' if default is not None else 'unspecified'
                def para_spacing(key,default):
                    for n,label in sources:
                        sp=find(n,'a:'+key)
                        if sp is not None and len(sp):
                            return {'kind':tag(sp[0]),'raw':int(sp[0].get('val')),'value':int(sp[0].get('val'))/(100000 if tag(sp[0])=='spcPct' else 100),'source':label}
                    return {'kind':'default','value':default,'source':'OOXML_default'}
                txt=''.join('\n' if tag(t)=='br' else (t.text or '') for t in p.xpath('.//a:t | .//m:t | .//a:br',namespaces=NS))
                run_txt=''.join(p.xpath('.//a:t/text() | .//m:t/text()',namespaces=NS))
                par={'slide':slide_no,'object_id':obj['id'],'paragraph_index':pi,'xpath':loc(p),'text':txt,'character_count':len(run_txt),'nonempty':bool(txt.strip()),'level':level,
                     'direct_properties':dict(pp.attrib) if pp is not None else {},'effective_properties':{},'runs':[]}
                for key,default in [('marL','0'),('indent','0'),('algn','l')]:
                    val,prov=para_attr(key,default); par['effective_properties'][key]={'value':int(val) if key!='algn' else val,'source':prov}
                par['hanging_indent']=par['effective_properties']['indent']['value']<0
                par['left_margin_pt']=par['effective_properties']['marL']['value']/12700
                par['first_line_offset_pt']=par['effective_properties']['indent']['value']/12700
                par['first_line_start_pt']=par['left_margin_pt']+par['first_line_offset_pt']
                par['line_spacing']=para_spacing('lnSpc',1.)
                par['space_before']=para_spacing('spcBef',0.)
                par['space_after']=para_spacing('spcAft',0.)
                for run in p.xpath('.//a:r | .//a:fld | .//m:r',namespaces=NS):
                    t=find(run,'a:t')
                    if t is None: t=find(run,'m:t')
                    if t is None or t.text is None: continue
                    text=t.text; rp=find(run,'a:rPr'); r_sources=[]
                    if rp is not None: r_sources.append((rp,'run'))
                    for n,label in sources:
                        dr=find(n,'a:defRPr')
                        if dr is not None: r_sources.append((dr,label+'_default_run'))
                    def run_attr(key,default=None):
                        for n,label in r_sources:
                            if key in n.attrib: return n.get(key),label
                        return default,'OOXML_default' if default is not None else 'unknown'
                    def run_child(path):
                        # Shape fontRef color overrides generic master-other text color.
                        for n,label in r_sources:
                            if label.startswith('master_otherStyle') or label.startswith('presentation_default'):
                                fr=find(shape,'p:style/a:fontRef')
                                if path=='a:solidFill' and fr is not None and len(fr): return fr,'shape_fontRef'
                            node=find(n,path)
                            if node is not None: return node,label
                        return None,'unknown'
                    size,size_src=run_attr('sz'); bold,bold_src=run_attr('b','0'); italic,italic_src=run_attr('i','0')
                    font,font_src=run_child('a:latin'); rawfont=font.get('typeface') if font is not None else None
                    fill,fill_src=run_child('a:solidFill'); col=color(fill,theme,cmap)
                    rec={'slide':slide_no,'object_id':obj['id'],'paragraph_index':pi,'xpath':loc(run),'text':text,'character_count':len(text),'nonspace_character_count':len(re.sub(r'\s','',text)),
                         'is_math':E.QName(run).namespace==NS['m'],'font_raw':rawfont,'font':theme_font(rawfont,theme),'font_source':font_src,
                         'size_pt':int(size)/100 if size is not None else None,'size_source':size_src,'bold':bold=='1','italic':italic=='1',
                         'color':col,'color_source':fill_src,'direct_rpr':dict(rp.attrib) if rp is not None else {}}
                    par['runs'].append(rec); obj['runs'].append(rec); all_runs.append(rec)
                obj['paragraphs'].append(par); all_paras.append(par)
        obj['text']='\n'.join(p['text'] for p in obj['paragraphs'])
        obj['character_count']=sum(r['character_count'] for r in obj['runs'])
        obj['nonempty_text']=bool(obj['text'].strip())
        obj['font_character_distribution']=dict(Counter({}))
        c=Counter()
        for r in obj['runs']: c[r['font']]+=r['character_count']
        obj['font_character_distribution']=dict(c)
        obj['dominant_font']=c.most_common(1)[0][0] if c else None
        c=Counter()
        for r in obj['runs']: c[r['size_pt']]+=r['character_count']
        obj['size_character_distribution']=dict(c)
        obj['dominant_size_pt']=c.most_common(1)[0][0] if c else None
        obj['role_heuristic']=('formula' if obj['runs'] and all(r['is_math'] for r in obj['runs']) else
                              'body' if obj['dominant_font']=='Times New Roman' else
                              'cover_or_closing_display' if obj['dominant_font']=='Elephant' and (obj['dominant_size_pt'] or 0)>=70 else
                              'metadata' if obj['dominant_font']=='Elephant' and (obj['dominant_size_pt'] or 0)<=20 else
                              'slide_title' if obj['dominant_font']=='Elephant' else 'other' if obj['nonempty_text'] else None)
        objects.append(obj); all_objects.append(obj)
    textobjects=[o for o in objects if o['nonempty_text']]
    rects=[o for o in objects if o['geometry']=='rect' and o['fill'] and o['fill']['hex']=='000000']
    pics=[o for o in objects if 'image' in o]
    fulltext='\n'.join(o['text'] for o in textobjects)
    slides.append({'slide':slide_no,'part':path,'layout_part':layout_path,'master_part':master_path,'theme_part':theme_path,
                   'object_count':len(objects),'text_object_count':len(textobjects),'image_count':len(pics),'black_rectangle_count':len(rects),
                   'character_count':sum(o['character_count'] for o in textobjects),'nonspace_character_count':len(re.sub(r'\s','',fulltext)),
                   'word_count_regex':len(re.findall(r"[A-Za-z0-9]+(?:[-'’][A-Za-z0-9]+)*",fulltext)),
                   'editable_text_box_union_slide_fraction':coverage([(o['bounds']['emu'],1) for o in textobjects if o['bounds']]),
                   'image_union_slide_fraction':coverage([(o['bounds']['emu'],1) for o in pics if o['bounds']]),
                   'black_mask_coverage':coverage([(o['bounds']['emu'],o['fill']['opacity']) for o in rects if o['bounds']],True),
                   'objects':objects})

def weighted_dist(key,rs):
    chars=Counter(); nonspace=Counter(); runs=Counter(); objs={}; pages={}
    for r in rs:
        val=key(r); chars[val]+=r['character_count']; nonspace[val]+=r['nonspace_character_count']; runs[val]+=1
        objs.setdefault(val,set()).add((r['slide'],r['object_id'])); pages.setdefault(val,set()).add(r['slide'])
    total=sum(chars.values()); nstotal=sum(nonspace.values())
    return [{'value':v,'characters':n,'character_fraction':n/total if total else 0,
             'nonspace_characters':nonspace[v],'nonspace_character_fraction':nonspace[v]/nstotal if nstotal else 0,'runs':runs[v],
             'objects_containing':len(objs[v]),'slides_containing':len(pages[v]),'slides':sorted(pages[v])} for v,n in chars.most_common()]
text_objects=[o for o in all_objects if o['nonempty_text']]
paras_nonempty=[p for p in all_paras if p['nonempty']]
ordinary_runs=[r for r in all_runs if not r['is_math']]
math_runs=[r for r in all_runs if r['is_math']]
black=[o for o in all_objects if o['geometry']=='rect' and o['fill'] and o['fill']['hex']=='000000']
images=[o for o in all_objects if 'image' in o]
roles={}
for role in sorted({o['role_heuristic'] for o in text_objects}):
    ros=[o for o in text_objects if o['role_heuristic']==role]; rrs=[r for o in ros for r in o['runs']]
    rps=[p for o in ros for p in o['paragraphs'] if p['nonempty']]
    roles[role]={'object_count':len(ros),'characters':sum(r['character_count'] for r in rrs),
                 'nonempty_paragraph_count':len(rps),'hanging_paragraph_count':sum(p['hanging_indent'] for p in rps),
                 'font_distribution':weighted_dist(lambda r:r['font'],rrs),'size_distribution':weighted_dist(lambda r:r['size_pt'],rrs),
                 'color_distribution':weighted_dist(lambda r:r['color']['hex'] if r['color'] else None,rrs),
                 'references':[{'slide':o['slide'],'id':o['id'],'text':o['text'],'bounds_inches':o['bounds']['inches'] if o['bounds'] else None} for o in ros]}
summary={'slide_count':len(slides),'canvas_emu':[W,H],'canvas_inches':[W/EMU,H/EMU],'aspect_ratio':W/H,
         'object_count':len(all_objects),'shape_count':sum(o['kind']=='sp' for o in all_objects),'picture_count':len(images),
         'text_object_count':len(text_objects),'paragraph_count_including_empty':len(all_paras),'nonempty_paragraph_count':len(paras_nonempty),
         'run_count':len(all_runs),'ordinary_run_count':len(ordinary_runs),'math_run_count':len(math_runs),
         'editable_character_count':sum(r['character_count'] for r in all_runs),'ordinary_character_count':sum(r['character_count'] for r in ordinary_runs),
         'math_character_count':sum(r['character_count'] for r in math_runs),
         'editable_nonspace_character_count':sum(r['nonspace_character_count'] for r in all_runs),
         'ordinary_nonspace_character_count':sum(r['nonspace_character_count'] for r in ordinary_runs),
         'math_nonspace_character_count':sum(r['nonspace_character_count'] for r in math_runs),
         'font_distribution_all_editable':weighted_dist(lambda r:r['font'],all_runs),
         'size_distribution_all_editable':weighted_dist(lambda r:r['size_pt'],all_runs),
         'color_distribution_all_editable':weighted_dist(lambda r:r['color']['hex'] if r['color'] else None,all_runs),
         'color_raw_distribution':weighted_dist(lambda r:json.dumps(r['color'],sort_keys=True),all_runs),
         'font_distribution_ordinary':weighted_dist(lambda r:r['font'],ordinary_runs),
         'size_distribution_ordinary':weighted_dist(lambda r:r['size_pt'],ordinary_runs),
         'font_dominant_object_distribution':dict(Counter(o['dominant_font'] for o in text_objects)),
         'size_dominant_object_distribution':dict(Counter(o['dominant_size_pt'] for o in text_objects)),
         'bold_characters':sum(r['character_count'] for r in all_runs if r['bold']),
         'italic_characters':sum(r['character_count'] for r in all_runs if r['italic']),
         'nonempty_hanging_paragraphs':sum(p['hanging_indent'] for p in paras_nonempty),
         'all_hanging_paragraphs':sum(p['hanging_indent'] for p in all_paras),
         'nonempty_paragraph_indent_distribution':dict(Counter(str((p['left_margin_pt'],p['first_line_offset_pt'])) for p in paras_nonempty)),
         'nonempty_paragraph_alignment_distribution':dict(Counter(p['effective_properties']['algn']['value'] for p in paras_nonempty)),
         'nonempty_line_spacing_distribution':dict(Counter(json.dumps(p['line_spacing'],sort_keys=True) for p in paras_nonempty)),
         'nonempty_space_before_distribution':dict(Counter(json.dumps(p['space_before'],sort_keys=True) for p in paras_nonempty)),
         'nonempty_space_after_distribution':dict(Counter(json.dumps(p['space_after'],sort_keys=True) for p in paras_nonempty)),
         'black_rectangle_count':len(black),'black_rectangle_opacity_distribution':dict(Counter(o['fill']['opacity'] for o in black)),
         'black_rectangle_full_canvas_count':sum(o.get('clipped_area_slide_fraction',0)>=.98 for o in black),
         'black_rectangle_slides':sorted({o['slide'] for o in black}),
         'image_background_candidates':sum(o.get('background_candidate',False) for o in images),
         'unique_image_media_parts':sorted({o['image']['media_part'] for o in images}),
         'images_with_xml_crop':sum(any(o['image']['crop_fractions'].values()) for o in images),
         'rotated_objects':sum(o['bounds'] is not None and o['bounds']['rotation_deg']!=0 for o in all_objects),
         'grouped_objects_requiring_manual_review':sum(o['kind']=='grpSp' for o in all_objects),
         'graphic_frames_requiring_manual_review':sum(o['kind']=='graphicFrame' for o in all_objects),
         'roles_heuristic':roles,
         'unknown_font_characters':sum(r['character_count'] for r in all_runs if r['font'] is None),
         'unknown_size_characters':sum(r['character_count'] for r in all_runs if r['size_pt'] is None),
         'unknown_color_characters':sum(r['character_count'] for r in all_runs if not r['color'] or not r['color']['hex'])}
result={'source':str(SOURCE),'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'methodology':{'scope':'Slide-level active Choice content; master/layout sample text, notes and raster labels excluded.',
          'character_weight':'Unicode code points inside text runs, including spaces; paragraph/line-break markers excluded.',
          'object_weight':'Each nonempty text-bearing shape has one vote based on its character-dominant font or size. Objects-containing distributions overlap.',
          'font':'Latin typeface declaration, resolving theme aliases. Actual font substitution at render time requires PowerPoint/font inspection.',
          'color':'OOXML theme mapping plus sRGB and HSL luminance transforms; resolved 8-bit hex may differ by one unit from Office rounding.',
          'geometry':'Axis-aligned bounds clipped to canvas. Coverage means object-box coverage, not glyph pixels or aesthetic blank space.',
          'inheritance':'Run > paragraph default > local list style > placeholder hierarchy > master text style > presentation default. Shape fontRef supplies color ahead of generic master otherStyle.',
          'default_spacing':'Absent inherited spacing recorded as single line, zero before/after per OOXML default. Verify renderer with COM if exact display needed.',
          'math':'Modern Choice OMML included separately; Fallback raster excluded. Declared 28 pt does not equal rendered subscript size.',
          'roles':'Reference-specific heuristic: Times New Roman = body; Elephant >=70pt = cover/closing display; Elephant <=20pt = metadata; other Elephant = slide title; all-math shape = formula. Inspect semantic classification before applying to another deck.',
          'limitations':['No image attribution or painting medium determined from XML.','No assumptions that every image is a paper screenshot.','Paragraph default spacing and shape fontRef inheritance need renderer corroboration.','No visual font substitution detection.','OOXML text margins use defaults when absent.']},
        'summary':summary,'slides':slides}
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'ooxml_metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['# OOXML quantitative evidence', '',
       f'Source: `{SOURCE}`',f'SHA-256: `{result["source_sha256"]}`','',
       'Scope: active slide-level Choice content. Raster image labels, notes and master sample text excluded.',
       'Character denominator includes spaces inside runs; excludes paragraph and manual line-break markers.',
       'Fonts are declared Latin typefaces, not verified render-time substitution. Role labels are reference-specific heuristics.', '',
       f'{len(slides)} slides; {W/EMU:.6f} × {H/EMU:.6f} inches; {len(all_objects)} active objects; {len(text_objects)} nonempty text objects; {len(paras_nonempty)} nonempty paragraphs.',
       f'{len(ordinary_runs)} ordinary runs / {summary["ordinary_character_count"]} characters, plus {len(math_runs)} math runs / {summary["math_character_count"]} characters.','',
       f'Nonspace counterpart: {summary["editable_nonspace_character_count"]} total = {summary["ordinary_nonspace_character_count"]} ordinary + {summary["math_nonspace_character_count"]} math characters. Whitespace is removed with Python Unicode regex \\s.', '',
       '## Font and size distributions (all editable characters)','','| Attribute | Value | Characters | Share | Nonspace chars | Nonspace share | Objects containing |','|---|---|---:|---:|---:|---:|---:|']
for category,key in [('Font','font_distribution_all_editable'),('Size (pt)','size_distribution_all_editable'),('Color (#)','color_distribution_all_editable')]:
    for d in summary[key]: lines.append(f'| {category} | {d["value"]} | {d["characters"]} | {d["character_fraction"]:.2%} | {d["nonspace_characters"]} | {d["nonspace_character_fraction"]:.2%} | {d["objects_containing"]} |')
lines+=['','Objects-containing counts overlap. Dominant-font counts instead assign one vote to each text object: '+json.dumps(summary['font_dominant_object_distribution']), '',
        '## Per-slide geometry and density','','| Slide | Editable chars | Regex words | Text boxes | Pictures | Black masks | Composite opacity: area | Mask union | Text-box union |','|---|---:|---:|---:|---:|---:|---|---:|---:|']
for s in slides:
    a=s['black_mask_coverage']['composited_opacity_area_distribution']
    bins='; '.join(f'{float(opacity):.2%}: {area:.2%}' for opacity,area in sorted(a.items(),key=lambda item:float(item[0])))
    lines.append(f'| {s["slide"]} | {s["character_count"]} | {s["word_count_regex"]} | {s["text_object_count"]} | {s["image_count"]} | {s["black_rectangle_count"]} | {bins} | {s["black_mask_coverage"]["union_slide_fraction"]:.2%} | {s["editable_text_box_union_slide_fraction"]:.2%} |')
lines+=['','Areas are clipped to the slide. Text-box area is not ink area and is not an aesthetic whitespace score.','',
        '## Role-specific evidence','']
for name,d in roles.items():
    lines += [f'### {name}',f'{d["object_count"]} objects, {d["characters"]} characters, {d["hanging_paragraph_count"]}/{d["nonempty_paragraph_count"]} nonempty paragraphs use hanging indentation.',
              'Sizes: '+', '.join(f'{x["value"]} pt: {x["characters"]} chars ({x["character_fraction"]:.2%})' for x in d['size_distribution']), '']
    for ref in d['references']: lines.append(f'- Slide {ref["slide"]}, shape {ref["id"]}, bounds inches {ref["bounds_inches"]}: {ref["text"]!r}')
    lines.append('')
lines+=['## Paragraph measurements','',
        f'{summary["nonempty_hanging_paragraphs"]}/{summary["nonempty_paragraph_count"]} all nonempty paragraphs are hanging. The body-role denominator is separately given above.',
        'Left margin / first-line offset distribution (pt): '+json.dumps(summary['nonempty_paragraph_indent_distribution']),
        'Line spacing distribution: '+json.dumps(summary['nonempty_line_spacing_distribution']),
        'Spacing before distribution: '+json.dumps(summary['nonempty_space_before_distribution']),
        'Spacing after distribution: '+json.dumps(summary['nonempty_space_after_distribution']), '',
        '## Mask and image measurements','',
        f'{len(black)} black rects; opacity-to-object-count distribution: {json.dumps(summary["black_rectangle_opacity_distribution"])}. {summary["black_rectangle_full_canvas_count"]} cover >=98% of the canvas after clipping.',
        'Composite alpha is 1 - product(1-alpha_i), hence two 50% black layers yield 75% opacity only in their overlap. Per-slide table gives exact clipped union and overlap.',
        f'{len(images)} pictures use {len(summary["unique_image_media_parts"])} distinct media parts; {summary["image_background_candidates"]} pictures cover >=85% of the slide, a geometric background heuristic.',
        f'{summary["images_with_xml_crop"]} pictures have explicit XML cropping; geometry may also place an image outside slide bounds. Screenshot font sizes and paper-source provenance cannot be inferred from bitmap placement.', '',
        '## Unknowns and reuse','',
        f'Unknown editable font characters: {summary["unknown_font_characters"]}; unknown font size: {summary["unknown_size_characters"]}; unknown color: {summary["unknown_color_characters"]}.',
        f'Grouped objects requiring manual review: {summary["grouped_objects_requiring_manual_review"]}; graphic frames: {summary["graphic_frames_requiring_manual_review"]}; rotated objects: {summary["rotated_objects"]}.',
        'This extractor targets ordinary ungrouped OOXML. For other decks, render and inspect if groups, charts, tables, custom color transforms, theme overrides or unusual placeholders are present. A group is counted as one object; its children are not recursively measured.',
        f'CLI: python {Path(__file__).name} INPUT.pptx --output-dir OUTPUT_DIRECTORY',
        'Dependencies: Python, lxml, Pillow. It never modifies the source PPTX. Full XML locations and inheritance provenance are retained in ooxml_metrics.json.']
(OUT/'ooxml_findings.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'slides':len(slides),'editable_characters':summary['editable_character_count'],'black_rectangle_opacities':summary['black_rectangle_opacity_distribution'],'output_dir':str(OUT.resolve())},ensure_ascii=False))
