import gc

import torch


class VRAMManager:
    @staticmethod
    def clear() -> None:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()
