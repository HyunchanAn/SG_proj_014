import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Determine project root and config path
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "configs" / "config.json"

class PipelineConfig:
    def __init__(self):
        # Load JSON config
        self._config = {}
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                self._config = json.load(f)
                
        # Parse configurations
        self.physical = self._config.get("physical_correction", {})
        self.workflow = self._config.get("workflow", {})
        self.rule_table = self._config.get("rule_table", {})

        # Physical Constants
        self.alpha = self.physical.get("alpha", 0.35)
        self.Ra_base = self.physical.get("Ra_base", 0.28)

        # Workflow Constants
        self.tolerance_percent = self.workflow.get("tolerance_percent", 5.0)
        
        # Rule Table
        self.processability_thickness_penalty = self.rule_table.get("processability_thickness_penalty", {})

        # External URLs (loaded from environment)
        self.MODULE_002_URL = os.getenv("MODULE_002_URL", "http://localhost:8002")
        self.MODULE_003_URL = os.getenv("MODULE_003_URL", "http://localhost:8003")
        self.MODULE_007_URL = os.getenv("MODULE_007_URL", "http://localhost:8007")
        self.MODULE_011_URL = os.getenv("MODULE_011_URL", "http://localhost:8011")
        self.MODULE_012_URL = os.getenv("MODULE_012_URL", "http://localhost:8012")
        self.MODULE_013_URL = os.getenv("MODULE_013_URL", "http://localhost:8013")
        self.MODULE_001_URL = os.getenv("MODULE_001_URL", "http://001-polysim:8001")
        self.MODULE_009_URL = os.getenv("MODULE_009_URL", "http://009-irgnn:8009")

        # n=10은 완전 경화(100% curing) 상태를 가정하기 위한 물리 스케일링 상수
        # 009 GNN 시뮬레이터 내부에서 weight_monomer = 1.0 / n 으로 분자 진동 강도를 스케일링하는 데 사용됨
        self.N_POLYMERIZATION = 10

# Singleton instance
config = PipelineConfig()
