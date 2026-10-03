"""Analysis settings: everything a user may need to adjust for their experiment.

Defaults match the BioFlo 120 E. coli batch-record form.
"""

from dataclasses import asdict, dataclass

GRAM_TYPES = ("negative", "positive", "not applicable")


@dataclass(frozen=True)  # frozen so a settings object can be used as a cache key in the app
class AnalysisSettings:
    organism: str = ""                   # blank = use the organism printed on the batch record
    gram_type: str = "negative"          # E. coli is Gram-negative (stains pink/red)
    pellet_volume_ml: float = 1.0        # culture volume spun down for each pellet
    temp_setpoint_c: float = 37.0
    temp_tolerance_c: float = 0.5
    od_linear_limit: float = 1.0         # the form: dilute if absorbance >= 1.0
    od_warning_level: float = 0.9        # readings just below the limit are likely already non-linear
    ph_offset_tolerance: float = 0.1
    pellet_tolerance_g: float = 0.0002   # balance reads to 0.0001 g
    time_tolerance_min: float = 2.0

    def __post_init__(self):
        if self.gram_type not in GRAM_TYPES:
            raise ValueError(f"gram_type must be one of {GRAM_TYPES}")

    def organism_for(self, record):
        return self.organism.strip() or record.header.get("organism", "")

    def as_rows(self):
        """(setting, value) pairs for the report and the Excel 'Settings' sheet."""
        labels = {
            "organism": "Organism", "gram_type": "Gram type", "pellet_volume_ml": "Pellet volume (mL)",
            "temp_setpoint_c": "Temperature setpoint (°C)", "temp_tolerance_c": "Temperature tolerance (± °C)",
            "od_linear_limit": "OD dilution limit (A600)", "od_warning_level": "OD warning level (A600)",
            "ph_offset_tolerance": "pH probe–meter tolerance", "pellet_tolerance_g": "Pellet calculation tolerance (g)",
            "time_tolerance_min": "Time tolerance (min)",
        }
        return [(labels[k], v if v != "" else "from batch record") for k, v in asdict(self).items()]
