"""Which structure the server can draw (owner, 2026-11-26): a valid one, or an R-group
scaffold RDKit refused only for its R tokens (DECIMER's [R1], [X]...: the prediction has
R-group labels, marcus.core.rgroups), which CDK reads as labelled atoms. Other invalid SMILES
are never sent to the tools worker. One rule: the depiction route and the API's
PredictionOut.drawable (which the UI reads) both use it."""


def is_drawable(smiles: str | None, valid: bool, rgroups: list[str] | None) -> bool:
    return bool(smiles) and (valid or bool(rgroups))
