import random
import string
from typing import Any, List, Dict, Optional


def generate_random_string(length: int = 10) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def generate_random_list(size: int = 5) -> List[int]:
    return [random.randint(0, 100) for _ in range(size)]


def shuffle_dict(d: dict) -> dict:
    keys = list(d.keys())
    random.shuffle(keys)
    return {k: d[k] for k in keys}


def generate_random_email() -> str:
    username = generate_random_string(8)
    domain = random.choice(["gmail.com", "yahoo.com", "example.com"])
    return f"{username}@{domain}"


def generate_random_phone() -> str:
    return f"+1-{random.randint(200, 999)}-{random.randint(100, 999)}-{random.randint(1000, 9999)}"


def generate_random_hex_color() -> str:
    return "#" + "".join(random.choices("0123456789ABCDEF", k=6))


def generate_random_ip() -> str:
    return ".".join(str(random.randint(0, 255)) for _ in range(4))


def generate_random_name() -> str:
    first_names = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Henry"]
    last_names = [
        "Smith",
        "Johnson",
        "Williams",
        "Brown",
        "Jones",
        "Garcia",
        "Miller",
        "Davis",
    ]
    return f"{random.choice(first_names)} {random.choice(last_names)}"


def sample_without_replacement(population: List[Any], k: int) -> List[Any]:
    return random.sample(population, k)


def weighted_random_choice(choices: Dict[Any, float]) -> Any:
    return random.choices(list(choices.keys()), weights=list(choices.values()))[0]


class RandomDataGenerator:
    def __init__(self, seed: Optional[int] = None):
        self.seed = seed
        if seed:
            random.seed(seed)

    def random_float(self, min_val: float = 0.0, max_val: float = 1.0) -> float:
        return random.uniform(min_val, max_val)

    def random_choice(self, items: list):
        return random.choice(items)

    def random_int(self, min_val: int = 0, max_val: int = 100) -> int:
        return random.randint(min_val, max_val)

    def random_bool(self) -> bool:
        return random.choice([True, False])  # type: ignore

    def random_bytes(self, length: int = 16) -> bytes:
        return bytes(random.randint(0, 255) for _ in range(length))

    def random_date(self, start_year: int = 2000, end_year: int = 2025) -> str:
        year = random.randint(start_year, end_year)
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        return f"{year:04d}-{month:02d}-{day:02d}"

    def random_uuid(self) -> str:
        return f"{generate_random_string(8)}-{generate_random_string(4)}-{generate_random_string(4)}-{generate_random_string(4)}-{generate_random_string(12)}"


class RandomCollection:
    def __init__(self, items: List[Any]):
        self.items = items

    def sample(self, k: int = 1) -> List[Any]:
        return random.sample(self.items, k)

    def shuffle(self) -> List[Any]:
        shuffled = self.items.copy()
        random.shuffle(shuffled)
        return shuffled


if __name__ == "__main__":
    generator = RandomDataGenerator(seed=42)
    print(generate_random_string())
    print(generate_random_list())
    print(generator.random_float())
    print(generate_random_email())
    print(generate_random_phone())
    print(generate_random_hex_color())
    print(generator.random_date())
    print(generator.random_uuid())
