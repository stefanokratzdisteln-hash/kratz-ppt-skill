# OOXML quantitative evidence

Source: `assets/reference.pptx`
SHA-256: `b7145583b355c512489aa4505278730d2023967aed598c9475fd4273b2225eef`

Scope: active slide-level Choice content. Raster image labels, notes and master sample text excluded.
Character denominator includes spaces inside runs; excludes paragraph and manual line-break markers.
Fonts are declared Latin typefaces, not verified render-time substitution. Role labels are reference-specific heuristics.

13 slides; 13.333333 × 7.500000 inches; 66 active objects; 22 nonempty text objects; 31 nonempty paragraphs.
107 ordinary runs / 1977 characters, plus 13 math runs / 29 characters.

Nonspace counterpart: 1758 total = 1732 ordinary + 26 math characters. Whitespace is removed with Python Unicode regex \s.

## Font and size distributions (all editable characters)

| Attribute | Value | Characters | Share | Nonspace chars | Nonspace share | Objects containing |
|---|---|---:|---:|---:|---:|---:|
| Font | Times New Roman | 1751 | 87.29% | 1525 | 86.75% | 10 |
| Font | Elephant | 226 | 11.27% | 207 | 11.77% | 11 |
| Font | Cambria Math | 29 | 1.45% | 26 | 1.48% | 1 |
| Size (pt) | 28.0 | 1062 | 52.94% | 938 | 53.36% | 6 |
| Size (pt) | 30.0 | 401 | 19.99% | 341 | 19.40% | 2 |
| Size (pt) | 24.0 | 317 | 15.80% | 272 | 15.47% | 3 |
| Size (pt) | 35.0 | 96 | 4.79% | 86 | 4.89% | 2 |
| Size (pt) | 40.0 | 80 | 3.99% | 74 | 4.21% | 5 |
| Size (pt) | 100.0 | 36 | 1.79% | 33 | 1.88% | 2 |
| Size (pt) | 18.0 | 14 | 0.70% | 14 | 0.80% | 2 |
| Color (#) | FFFFFF | 1339 | 66.75% | 1144 | 65.07% | 21 |
| Color (#) | 9DC3E6 | 408 | 20.34% | 372 | 21.16% | 8 |
| Color (#) | A9D18E | 182 | 9.07% | 171 | 9.73% | 10 |
| Color (#) | E080C0 | 61 | 3.04% | 56 | 3.19% | 3 |
| Color (#) | F4B183 | 16 | 0.80% | 15 | 0.85% | 2 |

Objects-containing counts overlap. Dominant-font counts instead assign one vote to each text object: {"Elephant": 11, "Times New Roman": 10, "Cambria Math": 1}

## Per-slide geometry and density

| Slide | Editable chars | Regex words | Text boxes | Pictures | Black masks | Composite opacity: area | Mask union | Text-box union |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| 1 | 22 | 3 | 2 | 1 | 1 | 50.00%: 44.35% | 44.35% | 44.61% |
| 2 | 253 | 34 | 2 | 2 | 3 | 50.00%: 16.44%; 75.00%: 83.56% | 100.00% | 48.93% |
| 3 | 8 | 1 | 1 | 2 | 2 | 50.00%: 0.05%; 75.00%: 99.95% | 100.00% | 2.31% |
| 4 | 391 | 50 | 1 | 2 | 2 | 50.00%: 0.05%; 75.00%: 99.95% | 100.00% | 53.82% |
| 5 | 79 | 11 | 1 | 2 | 2 | 50.00%: 0.05%; 75.00%: 99.95% | 100.00% | 12.35% |
| 6 | 203 | 28 | 1 | 1 | 2 | 50.00%: 0.05%; 75.00%: 99.95% | 100.00% | 30.56% |
| 7 | 134 | 18 | 1 | 2 | 2 | 50.00%: 0.05%; 75.00%: 99.95% | 100.00% | 16.19% |
| 8 | 17 | 4 | 1 | 2 | 1 | 50.00%: 50.68% | 50.68% | 3.99% |
| 9 | 233 | 35 | 4 | 2 | 1 | 50.00%: 50.68% | 50.68% | 29.26% |
| 10 | 209 | 30 | 2 | 2 | 1 | 50.00%: 79.01% | 79.01% | 26.12% |
| 11 | 225 | 35 | 2 | 1 | 2 | 50.00%: 50.05%; 75.00%: 49.95% | 100.00% | 43.36% |
| 12 | 204 | 32 | 2 | 1 | 2 | 50.00%: 56.54%; 75.00%: 43.46% | 100.00% | 33.79% |
| 13 | 28 | 4 | 2 | 1 | 1 | 50.00%: 44.35% | 44.35% | 44.61% |

Areas are clipped to the slide. Text-box area is not ink area and is not an aesthetic whitespace score.

## Role-specific evidence

### body
10 objects, 1751 characters, 18/18 nonempty paragraphs use hanging indentation.
Sizes: 28.0 pt: 1033 chars (58.99%), 30.0 pt: 401 chars (22.90%), 24.0 pt: 317 chars (18.10%)

- Slide 2, shape 21, bounds inches [0.296299, 2.618749, 6.379629, 4.341993]: 'Delta-radiomics measures changes in quantitative imaging features between scans taken at different time points. \n\nIt can help assess treatment response or disease progression earlier by detecting changes beyond tumor size alone.'
- Slide 4, shape 2, bounds inches [0.171538, 0.898147, 8.152536, 6.921242]: '1. Serial image acquisition\nCollect baseline and follow-up scans at defined treatment times.\n2. Image preprocessing\nImprove comparability through appropriate registration, resampling, and intensity normalization.\n3. ROI segmentation\nDelineate the tumor region at each time point.\n4. Radiomic feature extraction\nExtract corresponding shape, intensity, and texture features using consistent settings.\n'
- Slide 5, shape 2, bounds inches [0.171538, 0.898147, 8.152536, 1.514649]: '5. Delta feature calculation\nCalculate the change in each corresponding feature.'
- Slide 6, shape 2, bounds inches [0.171538, 0.898147, 8.152536, 3.748194]: '6. Feature selection\nSelect stable and informative features, and remove redundant features using training data.\n7. Model development\nTrain a prediction model for treatment response, survival, or recurrence.\n'
- Slide 7, shape 2, bounds inches [0.190057, 0.49074, 8.152536, 1.985873]: '8. Model evaluation\nEvaluate model performance using AUC, accuracy, sensitivity, and specificity, then validate it on independent data.'
- Slide 9, shape 5, bounds inches [5.823682, 2.611108, 5.185185, 1.716601]: 'Guo et al. used early MRI changes to predict pathological complete response (pCR) at surgery after treatment.'
- Slide 9, shape 8, bounds inches [5.859695, 5.768556, 5.853267, 0.908789]: '140 women — 98 training, 42 internal validation'
- Slide 10, shape 5, bounds inches [0.434791, 2.870051, 5.185185, 2.92832]: 'Delta outperformed baseline (p = 0.047); while the difference from cycle 1 was not significant (p = 0.500).\n\nSingle-center evidence; external validation is needed.'
- Slide 11, shape 8, bounds inches [1.060185, 3.120371, 11.212963, 3.635156]: 'Changes in scan settings or tumor boundaries can look like treatment effects.\nGuo’s results are encouraging, but validation in 42 patients from one hospital leaves a question: how well would the model work elsewhere?\n'
- Slide 12, shape 8, bounds inches [1.060185, 3.332043, 11.212963, 2.372949]: 'I would first test whether the same feature changes remain useful across hospitals.\nFor me, the key question is whether an early prediction helps doctors make a better treatment decision.'

### cover_or_closing_display
2 objects, 36 characters, 0/3 nonempty paragraphs use hanging indentation.
Sizes: 100.0 pt: 36 chars (100.00%)

- Slide 1, shape 7, bounds inches [0.464699, 2.016568, 13.389474, 3.466862]: 'Delta \nRadiomics'
- Slide 13, shape 7, bounds inches [0.464699, 2.016568, 13.389474, 3.466862]: 'Thanks for Listening!'

### formula
1 objects, 29 characters, 0/1 nonempty paragraphs use hanging indentation.
Sizes: 28.0 pt: 29 chars (100.00%)

- Slide 9, shape 6, bounds inches [6.101462, 5.069555, 5.416668, 0.615536]: 'Δ𝐹=𝐹before\xa0NAC−𝐹after\xa0cycle\xa01'

### metadata
2 objects, 14 characters, 0/2 nonempty paragraphs use hanging indentation.
Sizes: 18.0 pt: 14 chars (100.00%)

- Slide 1, shape 8, bounds inches [9.879161, 4.944358, 2.957895, 0.403906]: 'AIE1903'
- Slide 13, shape 8, bounds inches [9.879161, 4.944358, 2.957895, 0.403906]: 'AIE1903'

### slide_title
7 objects, 176 characters, 0/7 nonempty paragraphs use hanging indentation.
Sizes: 35.0 pt: 96 chars (54.55%), 40.0 pt: 80 chars (45.45%)

- Slide 2, shape 7, bounds inches [-0.484212, 0.425926, 14.305264, 1.592592]: 'Definition and Significance'
- Slide 3, shape 8, bounds inches [0.537037, 0.555564, 2.981481, 0.774154]: 'Workflow'
- Slide 8, shape 9, bounds inches [6.147759, 0.722223, 5.157797, 0.774154]: 'Guo et al. (2022)'
- Slide 9, shape 9, bounds inches [6.101462, 0.518518, 6.267836, 1.868066]: 'Predicting response after one chemotherapy cycle'
- Slide 10, shape 9, bounds inches [0.705629, 0.748729, 5.853268, 1.868066]: 'Delta features improved prediction over baseline'
- Slide 11, shape 7, bounds inches [0.62037, 1.724033, 3.351851, 0.774154]: 'Challenges'
- Slide 12, shape 7, bounds inches [0.62037, 1.279586, 4.962964, 1.44733]: 'Future development'

## Paragraph measurements

18/31 all nonempty paragraphs are hanging. The body-role denominator is separately given above.
Left margin / first-line offset distribution (pt): {"(0.0, 0.0)": 12, "(108.0, 0.0)": 1, "(56.69291338582677, -36.0)": 18}
Line spacing distribution: {"{\"kind\": \"default\", \"source\": \"OOXML_default\", \"value\": 1.0}": 23, "{\"kind\": \"spcPts\", \"raw\": 3360, \"source\": \"paragraph\", \"value\": 33.6}": 7, "{\"kind\": \"spcPct\", \"raw\": 100000, \"source\": \"paragraph\", \"value\": 1.0}": 1}
Spacing before distribution: {"{\"kind\": \"default\", \"source\": \"OOXML_default\", \"value\": 0.0}": 31}
Spacing after distribution: {"{\"kind\": \"default\", \"source\": \"OOXML_default\", \"value\": 0.0}": 19, "{\"kind\": \"spcPts\", \"raw\": 1200, \"source\": \"paragraph\", \"value\": 12.0}": 8, "{\"kind\": \"spcPts\", \"raw\": 1800, \"source\": \"paragraph\", \"value\": 18.0}": 4}

## Mask and image measurements

22 black rects; opacity-to-object-count distribution: {"0.5": 22}. 13 cover >=98% of the canvas after clipping.
Composite alpha is 1 - product(1-alpha_i), hence two 50% black layers yield 75% opacity only in their overlap. Per-slide table gives exact clipped union and overlap.
21 pictures use 12 distinct media parts; 13 pictures cover >=85% of the slide, a geometric background heuristic.
5 pictures have explicit XML cropping; geometry may also place an image outside slide bounds. Screenshot font sizes and paper-source provenance cannot be inferred from bitmap placement.

## Unknowns and reuse

Unknown editable font characters: 0; unknown font size: 0; unknown color: 0.
Grouped objects requiring manual review: 0; graphic frames: 0; rotated objects: 0.
This extractor targets ordinary ungrouped OOXML. For other decks, render and inspect if groups, charts, tables, custom color transforms, theme overrides or unusual placeholders are present. A group is counted as one object; its children are not recursively measured.
CLI: python audit_pptx.py INPUT.pptx --output-dir OUTPUT_DIRECTORY
Dependencies: Python, lxml, Pillow. It never modifies the source PPTX. Full XML locations and inheritance provenance are retained in ooxml_metrics.json.
