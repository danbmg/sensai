"""Données entièrement fictives, exclusivement destinées aux tests et à la démo."""
from sensai.memory.patients import PatientNotFoundError, PatientStore


DEMO_PATIENTS = (
    dict(patient_id="demo-dupont", name="Jeanne Dupont", birth_date="1958-03-12",
         allergies=["Pénicilline : urticaire et œdème de Quincke en 2019"],
         treatments=["Amlodipine 5 mg/j"],
         medical_history=["Hypertension artérielle", "Appendicectomie en 1989"],
         notes=["Dernière consultation : bilan tensionnel satisfaisant."]),
    dict(patient_id="demo-bernard", name="Louis Bernard", birth_date="1984-07-21",
         allergies=[], treatments=[], medical_history=[], notes=[]),
    dict(patient_id="demo-martin", name="Camille Martin", birth_date="1992-11-05",
         allergies=["Latex"], treatments=[], medical_history=["Asthme"], notes=[]),
)


def seed_demo_patients(store: PatientStore) -> list[dict]:
    """Crée seulement les dossiers absents ; préserve les notes et modifications existantes."""
    for patient in DEMO_PATIENTS:
        try:
            store.get_patient(patient["patient_id"])
        except PatientNotFoundError:
            store.create_patient(**patient)
    return [store.get_patient(patient["patient_id"]) for patient in DEMO_PATIENTS]
