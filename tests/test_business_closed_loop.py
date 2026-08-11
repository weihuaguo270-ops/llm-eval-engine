from examples.run_business_closed_loop import build_demo_report


def test_business_closed_loop_demo_has_independent_evidence():
    report = build_demo_report()
    assert report["dataset_audit"]["passed"] is True
    assert report["multimodal_evaluation"]["passed"] is True
    assert report["safety_evaluation"]["attack_success_rate"] == 0.0
    assert report["batch_drift"]["drift_detected"] is False
    assert report["release_decision"]["passed"] is True
    assert report["evidence_boundary"]["production_claim"] is False
