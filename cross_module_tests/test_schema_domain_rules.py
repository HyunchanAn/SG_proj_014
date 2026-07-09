import pytest
from pydantic import ValidationError
from src.schemas import Step2Target, Step1Metrics, OrchestrationRequest

def test_adhesion_domain_rule():
    # Valid case
    valid_target = Step2Target(
        target_initial_adhesion=100.0,
        target_aged_adhesion=500.0,
        target_tg=-20.0,
        target_viscosity=3000.0
    )
    assert valid_target.target_initial_adhesion == 100.0

    # Invalid case: initial > aged
    with pytest.raises(ValidationError) as exc_info:
        Step2Target(
            target_initial_adhesion=500.0,
            target_aged_adhesion=100.0,
            target_tg=-20.0,
            target_viscosity=3000.0
        )
    
    error_msg = str(exc_info.value)
    assert "초기 점착력이 후기 경시 점착력보다 클 수 없습니다" in error_msg

def test_tg_domain_rule():
    # Invalid case: Tg > 0
    with pytest.raises(ValidationError) as exc_info:
        Step2Target(
            target_initial_adhesion=100.0,
            target_aged_adhesion=500.0,
            target_tg=40.0,
            target_viscosity=3000.0
        )
    
    error_msg = str(exc_info.value)
    assert "less than or equal to 0" in error_msg

def test_orchestration_request_creation():
    metrics = Step1Metrics(
        surface_energy=45.0,
        roughness=0.5,
        gloss=100.0,
        curvature_radius=1.5
    )
    target = Step2Target(
        target_initial_adhesion=300.0,
        target_aged_adhesion=400.0,
        target_tg=-10.0,
        target_viscosity=2500.0
    )
    
    req = OrchestrationRequest(
        substrate_id="TEST_001",
        substrate_series="SGV",
        thickness_um=100.0,
        finish_type="Hairline",
        metrics=metrics,
        target=target,
        normal_vector_data=[0.0, 0.0, 1.0],
        material_stiffness=200000.0
    )
    assert req.substrate_series == "SGV"
    assert req.thickness_um == 100.0

def test_rdkit_smiles_validity():
    from rdkit import Chem
    # Valid smiles
    assert Chem.MolFromSmiles("C=CC(=O)O") is not None
    # Invalid smiles
    assert Chem.MolFromSmiles("InvalidSmilesString!!!") is None
