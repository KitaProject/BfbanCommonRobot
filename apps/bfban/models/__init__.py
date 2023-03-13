from pydantic import BaseModel
from humps.camel import case


def to_camel(string):
    return case(string)


class CamelModel(BaseModel):
    class Config:
        alias_generator = to_camel
        allow_population_by_field_name = True


class WeaponStatus(CamelModel):
    weapon_name: str
    weapon_type: str
    played_sec: int
    kills: int
    kpm: float
    acc: float
    fired: int
    hits: int
    head_shots: int
    head_shots_kill_ratio: float
    hit_per_kills: float

    def __str__(self):
        return f"{self.weapon_name} 种类: {self.weapon_type} 击杀数: {self.kills} KPM: {self.kpm} 准确度: {self.acc}% 爆头率: {self.acc}% 效率: {self.hit_per_kills}"


class VehicleModel(CamelModel):
    name: str
    type: str
    image_url: str
    kills: int = 0
    kpm: float = 0
    played_sec: int = 0
    rank: int = 0
    progression: float = 0
    destroy: int = 0

    def __str__(self):
        return f"{self.name} 种类: {self.type} 击杀数: {self.kills} KPM: {self.kpm} 摧毁: {self.destroy}"


class AllStatusModel(CamelModel):
    name: str | None
    avatar_url: str | None
    pid: int = 0
    played_sec: int = 0
    played_time: str = "10小时2分"
    rank: int = 0
    kills: int = 0
    deaths: int = 0
    kdr: float = 0
    head_shots: int = 0
    head_shots_kill_ratio: float = 0
    spm: float = 0
    kpm: float = 0
    accuracy: float = 0
    wins: int = 0
    win_percent: float = 0
    losses: int = 0
    revives: int = 0
    dog_tags_taken: int = 0
    rounds_played: int = 0
    highest_kill_streak: int = 0
    longest_head_shot: int = 0
    platoon: str = ""
    weapons: list[WeaponStatus] = None
    vehicles: list[VehicleModel] = None

    def get_stats_info(self):
        stats = f"生涯数据:<br>等级: {self.rank}  游戏时间: {self.played_time}  KPM: {self.kpm}  KD: {self.kdr}   " \
                f"KILLS: {self.kills}   SPM: {self.spm}  胜率: {self.win_percent}%"

        self.weapons.sort(key=lambda weapon: weapon.kills, reverse=True)
        self.vehicles.sort(key=lambda vehicle: vehicle.kills, reverse=True)

        limit = 100 if self.kills > 2000 else 60
        weapons_stats = "<br>".join((str(weapon) for weapon in self.weapons if weapon.kills > limit))
        vehicles_stats = "<br>".join((str(vehicle) for vehicle in self.vehicles if vehicle.kills > 100))

        if weapons_stats == "":
            weapons_stats = "数据不足"

        if vehicles_stats == "":
            vehicles_stats = "数据不足"

        return f"{stats}<br>武器数据：{weapons_stats}<br>载具数据：{vehicles_stats}"
