import json
from pathlib import Path
from loguru import logger
from rdkit import Chem

# Load monomer mappings from JSON file
BASE_DIR = Path(__file__).resolve().parent.parent
MAPPING_FILE_PATH = BASE_DIR / "data" / "monomer_mapping.json"

def load_monomer_mappings() -> dict:
    """Load monomer to SMILES mapping from mapping file."""
    if not MAPPING_FILE_PATH.exists():
        logger.error(f"Monomer mapping file not found at: {MAPPING_FILE_PATH}")
        return {}
    try:
        with open(MAPPING_FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error reading monomer mapping file: {e}")
        return {}

# Cache mappings globally
MONOMER_SMILES_MAP = load_monomer_mappings()

def convert_recipe_to_components(recipe: dict, n_polymerization: int) -> list[dict]:
    """
    Convert monomer recipe to 009 API payload components.
    Performs RDKit chemical validation (including valence checks) on SMILES string.
    Raises ValueError with high-quality error message if check fails.
    """
    components = []
    for monomer, ratio in recipe.items():
        # 1. Fetch SMILES
        smiles = MONOMER_SMILES_MAP.get(monomer)
        if not smiles:
            logger.error(f"Monomer mapping not found for abbreviation: '{monomer}'")
            raise ValueError(
                f"Monomer mapping not found for abbreviation: '{monomer}'. "
                f"Please update 'monomer_mapping.json' with a valid SMILES definition."
            )
        
        # 2. RDKit validation (built-in sanitization catches valence errors)
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.error(f"RDKit validation failed for monomer '{monomer}': '{smiles}'")
            raise ValueError(
                f"Invalid SMILES for monomer '{monomer}': {smiles}. "
                f"RDKit could not parse the molecule or detected valence errors."
            )
            
        components.append({
            "smiles": smiles,
            "ratio": float(ratio),
            "n": n_polymerization
        })
    return components

def extract_gnn_features(gnn_response: dict) -> list[float]:
    """
    Extract transmittance features from 009 GNN response.
    Returns a default list of [0.0, 0.0, 0.0] if data is missing.
    """
    if not gnn_response or "transmittance" not in gnn_response:
        logger.warning("GNN response does not contain 'transmittance'. Returning default features.")
        return [0.0, 0.0, 0.0]
    
    transmittance = gnn_response["transmittance"]
    if not isinstance(transmittance, list):
        logger.warning(f"Expected transmittance to be list, got {type(transmittance)}. Returning default.")
        return [0.0, 0.0, 0.0]
        
    return [float(x) for x in transmittance]
