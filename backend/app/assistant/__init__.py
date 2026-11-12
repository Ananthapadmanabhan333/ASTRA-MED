"""Source-grounded medical data assistant (phase 5).

It answers questions about ASTRA-MED's simulated crew data, its documentation and the NASA open data
already ingested, with a citation for every statement. It never diagnoses, never recommends or
prescribes treatment, flags missing information, keeps established documentation apart from
experimental model output, and escalates potentially serious situations to the flight surgeon.
"""

ASSISTANT_DISCLAIMER = (
    "The assistant explains simulated data and documented system behaviour. It does not diagnose, "
    "recommend treatment or prescribe medication, and it is not clinically validated. Potentially "
    "serious situations must go to qualified medical personnel (the flight surgeon)."
)
