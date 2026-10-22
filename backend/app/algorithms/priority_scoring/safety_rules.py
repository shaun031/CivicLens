def verified_hazard(hazard: dict, epoch: int) -> bool:
    return bool(
        hazard.get("flag")
        and hazard.get("status") == "VERIFIED"
        and hazard.get("epoch") == epoch
        and hazard.get("evidenceReferences")
        and hazard.get("assessedBy")
        and len(hazard.get("reason", "").strip()) >= 10
    )
