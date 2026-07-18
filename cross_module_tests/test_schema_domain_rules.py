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

def test_monomer_mapper_validation_failures():
    from src.utils import monomer_mapper
    import pytest

    # 1. Test missing monomer in mapping json (now skips and returns empty list after PubChem fails)
    result = monomer_mapper.convert_recipe_to_components({"UNKNOWN_MONOMER": 0.5}, 10)
    assert result == []

    # 2. Test invalid SMILES syntax
    # Temporarily insert an invalid mapping to mapping dictionary to trigger parse error
    monomer_mapper.MONOMER_SMILES_MAP["BAD_SYNTAX"] = "Invalid_SMILES_String"
    try:
        with pytest.raises(ValueError) as exc_info:
            monomer_mapper.convert_recipe_to_components({"BAD_SYNTAX": 0.5}, 10)
        assert "Invalid SMILES for monomer" in str(exc_info.value)
        assert "could not parse the molecule" in str(exc_info.value)
    finally:
        del monomer_mapper.MONOMER_SMILES_MAP["BAD_SYNTAX"]

    # 3. Test valence error (chemical valence violation: 5-valent carbon)
    # RDKit MolFromSmiles will fail sanitization and return None for C(=O)(=O)(=O)O
    monomer_mapper.MONOMER_SMILES_MAP["VALENCE_ERR"] = "C(=O)(=O)(=O)O"
    try:
        with pytest.raises(ValueError) as exc_info:
            monomer_mapper.convert_recipe_to_components({"VALENCE_ERR": 0.5}, 10)
        assert "Invalid SMILES for monomer" in str(exc_info.value)
        assert "valence errors" in str(exc_info.value)
    finally:
        del monomer_mapper.MONOMER_SMILES_MAP["VALENCE_ERR"]
