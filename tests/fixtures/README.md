# Test fixtures

## guv_overview.czi

One real overview image from the automation, 512 x 512 px, three channels (AF488, RhodB,
T-PMT), 0.414 um/px, acquired 2026-08-26 on the GUV run `adaptive_zsan_GUV`. Source:
`data/I_visit/adaptive_zsan_GUV/image_for_analysis/50e8c1ba-86f6-40c3-9b80-91849b7a002b_Image_overview.czi`.

It is the file the pipeline ran its overview analysis on (preset `Cellpose`), and that run
found two GUVs. Their stage positions are the expected values in
`tests/world_b/test_overview_analysis.py`.

Changed from the original, byte for byte with text of the same length, so that the structure of
the file is untouched (pixels and the metadata read by `IO/read_czi_file.py` are identical):

| What | Original | Now |
|---|---|---|
| microscope serial number (3x) | the real one | `0000000000` |
| `Information/Document/UserName` | ZEN account name | `xxxxx` |
| ZEN save folders (3x) | `D:\<account>\Pictures` | `D:\xxxxx\Pictures` |
