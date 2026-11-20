import sys; sys.path.insert(0, "src")
from textutil import slugify
def test_basic(): assert slugify("Hello, World!") == "hello-world"
def test_spaces(): assert slugify("  Many   spaces here ") == "many-spaces-here"
def test_accents(): assert slugify("Ação Rápida") == "acao-rapida"
def test_empty(): assert slugify("   ") == ""
