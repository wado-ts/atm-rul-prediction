"""
Fleet-wide constants.

Each ATM has exactly 5 components predicted independently, each by its own
model. Component identifiers are fixed placeholders until real component
names are assigned.
"""
COMPONENT_IDS: list[str] = [
    "CMD_CAS_1",
    "CMD_CAS_2",
    "CMD_CAS_3",
    "CMD_CAS_4",
    "RECE_PRINT",
]
