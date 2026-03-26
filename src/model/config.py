# game_config.py (Corrected Version)

class GameConfig:
    def __init__(self):
        self.data = {
            "cannon_player": "Human",  # "Human" 或 "AI"
            "soldier_player": "AI",    # "Human" 或 "AI"
            "depth": 12,
            "time_limit": 15.0,
            "depth": 12,
            "time_limit": 15.0,
            "threads": 12,
            "use_tablebase": True  # 是否启用残局库预查
        }
    
    def get_all(self):
        """返回所有配置设置的副本"""
        return self.data.copy()
    
    def update(self, new_settings: dict):
        """批量更新配置"""
        for key, value in new_settings.items():
            if key in self.data:
                self.data[key] = value
    
    # is_ai_turn 方法可以被 Orchestrator 的内部逻辑取代，但保留也无妨
    def is_ai_turn(self, current_player):
        from core.game_logic import CANNON, SOLDIER
        if current_player == CANNON:
            return self.data["cannon_player"] == "AI"
        elif current_player == SOLDIER:
            return self.data["soldier_player"] == "AI"
        return False