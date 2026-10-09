from hypothesis import settings

# Selected with `pytest --hypothesis-profile=ci`.
settings.register_profile("ci", max_examples=200)
