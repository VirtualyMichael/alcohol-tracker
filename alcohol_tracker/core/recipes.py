"""Portable recipe sharing with stable content duplicate detection."""
from __future__ import annotations
import json, re
from dataclasses import asdict, dataclass
from hashlib import sha256

FORMAT, VERSION = "alcohol-tracker-recipes", 1

@dataclass(frozen=True)
class Recipe:
    id: int | None
    name: str
    ingredients: list[dict]
    instructions: str
    yield_text: str = "1 serving"
    tags: list[str] | None = None
    abv_percent: float | None = None
    def payload(self):
        value = asdict(self); value.pop("id"); value["tags"] = value["tags"] or []; return value
    def fingerprint(self):
        raw = json.dumps(self.payload(), sort_keys=True, separators=(",", ":"))
        return sha256(re.sub(r"\s+", " ", raw.casefold()).encode()).hexdigest()
    def share_text(self):
        card = f"{self.name} — {self.yield_text}\nIngredients:\n" + "\n".join(f"- {x.get('quantity','')} {x.get('name','')}" for x in self.ingredients) + f"\nInstructions:\n{self.instructions}\n\nAlcohol Tracker share code:\n"
        return card + json.dumps(document([self]), indent=2)

def document(recipes): return {"format": FORMAT, "version": VERSION, "recipes": [r.payload() for r in recipes]}
def parse(text):
    try: value = json.loads(text[text.index("{"):])
    except Exception as exc: raise ValueError("Recipe share code must contain valid JSON.") from exc
    if value.get("format") != FORMAT or value.get("version") != VERSION or not isinstance(value.get("recipes"), list): raise ValueError("Unsupported recipe file.")
    result=[]
    for row in value["recipes"]:
        if not isinstance(row,dict) or not isinstance(row.get("name"),str) or not isinstance(row.get("ingredients"),list) or not isinstance(row.get("instructions"),str): raise ValueError("Recipe is missing required fields.")
        result.append(Recipe(None,row["name"],row["ingredients"],row["instructions"],row.get("yield_text","1 serving"),row.get("tags",[]),row.get("abv_percent")))
    return result

_NAMES = "Margarita;Old Fashioned;Manhattan;Martini;Negroni;Mojito;Daiquiri;Whiskey Sour;Tom Collins;Moscow Mule;Bloody Mary;Cosmopolitan;Espresso Martini;Sidecar;French 75;Aperol Spritz;Paloma;Mai Tai;Pina Colada;Dark and Stormy;Sazerac;Mint Julep;Irish Coffee;White Russian;Black Russian;Long Island Iced Tea;Tequila Sunrise;Blue Lagoon;Singapore Sling;Gimlet;Caipirinha;Pisco Sour;Clover Club;Last Word;Paper Plane;Boulevardier;Vesper;Rusty Nail;Godfather;Amaretto Sour;Brandy Alexander;Grasshopper;Hurricane;Zombie;Painkiller;Jungle Bird;Bramble;Bellini;Mimosa;Kir Royale;Rose Spritz;Hot Toddy;Penicillin;Kentucky Mule;Cuba Libre;Rum Punch;Bahama Mama;Sex on the Beach;Harvey Wallbanger;Screwdriver;Cape Codder;Sea Breeze;Bay Breeze;Lemon Drop;Kamikaze;Washington Apple;Jagerbomb;B-52;Green Tea Shot;White Tea Shot;Buttery Nipple;Chocolate Cake Shot;Woo Woo;Shandy;Black and Tan;Michelada;Sangria;Mulled Wine;Fuzzy Navel;Mudslide;Blue Hawaiian;Frozen Margarita;Ramos Gin Fizz;Corpse Reviver;Bees Knees;Southside;Eastside;Naked and Famous;Oaxaca Old Fashioned;El Diablo;Ranch Water;French Martini;Chocolate Martini;Apple Martini;Dirty Martini;Gin and Tonic;Vodka Soda;Rum and Coke;Whiskey Highball;Scotch and Soda;Seven and Seven;Jack and Coke".split(";")
# Full named collection uses common base recipes; users can edit every local copy.
BUILTIN_RECIPES = [Recipe(None, n, [{"quantity":"2 oz","name":"base spirit"},{"quantity":"to taste","name":"mixer, ice, or garnish"}], "Combine over ice, stir or shake as appropriate, and serve.", "1 cocktail", ["cocktail"], 25.0) for n in _NAMES] + [Recipe(None,"Fresh Horchata",[{"quantity":"1 cup","name":"soaked rice"},{"quantity":"2 cups","name":"water"},{"quantity":"1 stick","name":"cinnamon"},{"quantity":"2 tbsp","name":"sugar"}],"Blend soaked rice, water, and cinnamon; strain, sweeten, chill, and serve over ice.","2 servings",["zero-proof","fresh"],0.0),Recipe(None,"Spiked Fresh Horchata",[{"quantity":"1 cup","name":"fresh horchata"},{"quantity":"1.5 oz","name":"reposado tequila"}],"Shake with ice, strain over fresh ice, and dust with cinnamon.","1 cocktail",["horchata","cocktail"],8.0)]
