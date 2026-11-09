# Heat hazard and exposure index (definition)

Status: draft for the README. Weights are judgment calls, not estimated from data.

Unit: 500 m grid cell, Greater Mumbai (BMC), core cells only.

Components (each standardised across core cells, mean 0, standard deviation 1, ddof 0):
- H: land surface temperature (Landsat 8 and 9 composite of clear days, March heavy).
- S: built-up versus green surface, standardised(minus z NDVI plus z NDBI). This is land cover, hazard side. It is not social sensitivity.
- E: population exposure, standardised raw pop_density_land (WorldPop 2020 over land footprint).

Primary index: 0.4 H + 0.4 S + 0.2 E (candidate name W3_raw).
Matched without exposure: 0.5 H + 0.5 S (candidate name W4_noexp).

Hotspots are reported as a zone (top 180 cells, about the top 10 percent), never as a ranked 20 cell list.

Known limits:
- LST is surface temperature, not air temperature, and the composite is a few clear days.
- H and S are strongly correlated and LST is largely explained by NDVI and NDBI, so the index is mostly one heat and built-up axis.
- The exposure weight 0.2 is arbitrary. Sensitivity to 0 and one third is a later step.
- No age, income or housing data are used. The map is a hazard and exposure map, not a vulnerability map.
- Cells with thin observations or zero population are flagged low confidence.
