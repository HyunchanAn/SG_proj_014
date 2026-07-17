import json
import requests
from pathlib import Path
from loguru import logger
from rdkit import Chem

# Blacklist for obvious dummy features and invalid inputs
DUMMY_BLACKLIST = {"1", "A", "___", "____41", "None", "NaN", "null", ""}

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

def save_monomer_mappings(mapping: dict) -> None:
    """Save monomer mapping back to JSON file."""
    try:
        MAPPING_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(MAPPING_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving monomer mapping file: {e}")

def fetch_smiles_from_pubchem(monomer_name: str) -> str:
    """Fetch SMILES from PubChem REST API by compound name."""
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{monomer_name}/property/CanonicalSMILES,IsomericSMILES/JSON"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            properties = data.get("PropertyTable", {}).get("Properties", [])
            if properties:
                props = properties[0]
                return props.get("CanonicalSMILES") or props.get("IsomericSMILES") or props.get("ConnectivitySMILES") or props.get("SMILES")
    except requests.exceptions.RequestException as e:
        logger.warning(f"PubChem API connection error for {monomer_name}: {e}")
    except Exception as e:
        logger.warning(f"Error parsing PubChem response for {monomer_name}: {e}")
    return None

# Cache mappings globally
MONOMER_SMILES_MAP = load_monomer_mappings()
FAILED_MONOMERS_CACHE = set()

def convert_recipe_to_components(recipe: dict, n_polymerization: int) -> list[dict]:
    """
    Convert monomer recipe to 009 API payload components.
    Performs RDKit chemical validation (including valence checks) on SMILES string.
    Raises ValueError with high-quality error message if check fails.
    """
    components = []
    mapping_updated = False
    
    for monomer, ratio in recipe.items():
        # Skip if monomer is obviously a dummy feature (starts with _ or in blacklist)
        if not monomer or monomer.startswith("_") or monomer in DUMMY_BLACKLIST:
            continue
        
        # Skip if we already failed to fetch it in this session to prevent spam
        if monomer in FAILED_MONOMERS_CACHE:
            continue
        
        # 1. Fetch SMILES
        smiles = MONOMER_SMILES_MAP.get(monomer)
        
        # Fallback to PubChem if not found
        if not smiles:
            logger.info(f"Monomer '{monomer}' not found in mapping. Querying PubChem...")
            smiles = fetch_smiles_from_pubchem(monomer)
            if smiles:
                logger.info(f"Successfully fetched SMILES for '{monomer}' from PubChem: {smiles}")
                MONOMER_SMILES_MAP[monomer] = smiles
                mapping_updated = True
            else:
                logger.warning(f"PubChem fallback failed for '{monomer}'. Adding to failed cache and skipping.")
                FAILED_MONOMERS_CACHE.add(monomer)
                continue
        
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
        
    if mapping_updated:
        save_monomer_mappings(MONOMER_SMILES_MAP)
        logger.info("Updated monomer_mapping.json with new PubChem records.")
        
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
