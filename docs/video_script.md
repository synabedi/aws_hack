# Video script (3:00) — JalMaapi

Rules: product on screen within 40 s; every simulated element labelled; limitations on screen; AWS console visible;
news clips credited; measured numbers read out unedited. Record 1080p, 30 fps, screen captures at 100% zoom, dark theme.

| Time | On screen | Voiceover |
| --- | --- | --- |
| 0:00–0:20 | Sept 2026 IGI T3 underpass flooding clip (ThePrint, credited), 2024 Siraspur headline (Deccan Herald), card "448 hotspots · 179 cameras · 45 spots" | Every monsoon Delhi floods the same few hundred points. Its control room watches 179 cameras at 45 of them, by eye. We found no report of anyone measuring depth from those cameras. |
| 0:20–0:35 | A wall of camera feeds; text "6 to 8 inches: field staff phone the control room" | One named officer per hotspot decides when to close it, from a phone call and a camera wall. |
| 0:35–1:15 | Dashboard, City view. Click the DTU site. Dry twin point cloud orbit (or heightmap) → staged flood frame → SAM 2.1 mask → waterline lit on the twin → level locks → depth heat map with "__ ± __ cm" | Water is level, and the ground does not move. On a dry day a phone walk-through gives a metric 3D model of the dip. In a flood frame the water's edge meets that model, and its height is the water level. Depth everywhere follows. No gauge board, no sensor, no car in frame. Builds on published camera-gauge work (cite on screen: Eltner 2021, Dale 2026). |
| 1:15–1:40 | Split screen: staged flood with the ruler and the system's number; `validation/report.md` table filling: MAE __ cm, worst __ cm, within ±2σ __% | We flooded a spot on campus with a hose and read a ruler every 30 seconds. Here is how wrong we are: mean error __ centimetres, worst __ . Our error bar covered the truth __ percent of the time. |
| 1:40–2:05 | Site view: depth so far, fitted model, forecast band, verdict cards "small car: NO ENTRY in 14 min" | The depth curve plus the basin shape fits a two-parameter physics model. Integrate it forward and you get when, not just how deep. Predicted time to the closure level from the first 40% of the fill: __ s vs __ s actual. |
| 2:05–2:35 | City view with SIM tags, Pumps view (plan vs baseline numbers), Approvals: officer id, Approve → Hindi and English advisory. AWS console: App Runner service, Bedrock model access, DynamoDB tables | Six more hotspots are simulated and labelled. Strands agents on Bedrock plan pumps with the model; the arithmetic runs in Python. Cedar policy: no closure publishes without the officer. One tap, logged, Hindi and English. |
| 2:35–2:50 | Drain health view; "outlet open vs partly blocked: k = __ vs __" | How fast a site drains is a number too. Block the outlet and the drain coefficient drops by __ . That flags choked drains from footage alone. |
| 2:50–3:00 | `docs/architecture.png`; limitations list on screen | Every hotspot camera can become a gauge. Not proven yet: night, rain on the lens, a real monsoon. One staged test, one real site. Here is the code. |

Fill every `__` from `validation/report.md` only. If a number is missing when recording, say "not measured yet", do not estimate.
