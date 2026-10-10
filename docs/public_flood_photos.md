# Segmentation on public flood photos (qualitative, Sat 10 Oct 2026, 17:55 IST)

`docs/segmentation_public_photos.jpg` shows six Wikimedia Commons photos of flooded underpasses
(left), the SAM 2.1 mask (middle) and the OpenCV GrabCut fallback mask (right). **No prompt** was given:
both ran from the weak lower-frame prior only, so this is the worst case; in the pipeline the prompt is a
box from the vision model or a click. Run on an Apple M5 CPU with `facebook/sam2.1-hiera-tiny`.

| # | Photo | SAM 2.1 | GrabCut |
| --- | --- | --- | --- |
| 1 | Oestrich underpass | Water covered; wet verge at left partly included | Leaks onto bridge abutments |
| 2 | Hengrove underpass | Water covered up to the dark tunnel mouth | Leaks onto right wall and bushes |
| 3 | Belfast Broadway ramp (2) | Water covered; **leaks onto the concrete ramp at left** (classic wet-pavement failure) | Same leak, larger |
| 4 | Belfast Broadway (1) | Clean water mask, ramp walls excluded | Clean |
| 5 | Quarley underpass | Water covered; wet kerb strips partly included | Leaks onto both walls |
| 6 | Calgary flooded street | Water covered; cones and the splash excluded | Leaks onto the whole wet road |

What this says: segmentation, not geometry, will set the error floor (architecture doc 8.2). The box prompt
and the "keep waterline pixels on steep surfaces" rule exist for exactly photo 3. Nothing here is a measurement;
there is no depth ground truth for these photos.

## Attribution (all CC BY-SA, resized, used for a qualitative check only)

1. "Flooded underpass in Oestrich 20150111 4" — CC BY-SA 4.0 — https://commons.wikimedia.org/wiki/File:Flooded_underpass_in_Oestrich_20150111_4.jpg
2. "Flooded Underpass at Hengrove" (geograph.org.uk 7053272) — CC BY-SA 2.0 — https://commons.wikimedia.org/wiki/File:Flooded_Underpass_at_Hengrove_-_geograph.org.uk_-_7053272.jpg
3. "Flooded Broadway underpass, Belfast (2)" (geograph.org.uk 925752) — CC BY-SA 2.0 — https://commons.wikimedia.org/wiki/File:Flooded_Broadway_underpass,_Belfast_(2)_-_geograph.org.uk_-_925752.jpg
4. "Flooded Broadway underpass, Belfast (1)" (geograph.org.uk 925736) — CC BY-SA 2.0 — https://commons.wikimedia.org/wiki/File:Flooded_Broadway_underpass,_Belfast_(1)_-_geograph.org.uk_-_925736.jpg
5. "Quarley - Flooded Underpass" (geograph.org.uk 1154543) — CC BY-SA 2.0 — https://commons.wikimedia.org/wiki/File:Quarley_-_Flooded_Underpass_-_geograph.org.uk_-_1154543.jpg
6. "A car splashes up water as it drives down a flooded street in Calgary, Alberta, Canada" — CC BY-SA 4.0 — https://commons.wikimedia.org/wiki/File:A_car_splashes_up_water_as_it_drives_down_a_flooded_street_in_Calgary,_Alberta,_Canada.jpg
