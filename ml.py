def recommend_antibiotic(symptoms: dict) -> dict:
    fever = float(symptoms.get("fever", 0))
    wbc = float(symptoms.get("wbc", 0))
    crp = float(symptoms.get("crp", 0))
    cough = symptoms.get("cough") == "Yes"
    sore_throat = symptoms.get("sore_throat") == "Yes"
    rapid = symptoms.get("rapid_test") == "Yes"
    breath = symptoms.get("breath") == "Yes"
    chest_pain = symptoms.get("chest_pain") == "Yes"
    travel = symptoms.get("travel") == "Yes"
    comorbidity = symptoms.get("comorbidity") == "Yes"

    reasons = []

    # Rule 1
    if fever > 38 and wbc > 12 and crp > 20:
        reasons.append("High fever, WBC, and CRP suggest bacterial infection")
        return {"needs": True, "antibiotic": "Amoxicillin/Clavulanate", "reasons": reasons}

    # Rule 2
    if rapid:
        reasons.append("Rapid test positive for bacterial pathogen")
        return {"needs": True, "antibiotic": "Azithromycin", "reasons": reasons}

    # Rule 3: severe symptoms
    if breath or chest_pain:
        reasons.append("Severe respiratory symptoms present")
        return {"needs": True, "antibiotic": "Levofloxacin", "reasons": reasons}

    # Rule 4: comorbidities / risk
    if comorbidity and fever > 37.5:
        reasons.append("High-risk patient with comorbidity and fever")
        return {"needs": True, "antibiotic": "Ceftriaxone", "reasons": reasons}

    # Rule 5: travel risk
    if travel and fever > 38:
        reasons.append("Recent travel history with fever → possible resistant strain")
        return {"needs": True, "antibiotic": "Doxycycline", "reasons": reasons}

    # Default
    reasons.append("Insufficient evidence for antibiotics; monitor and run further tests")
    return {"needs": False, "antibiotic": None, "reasons": reasons}