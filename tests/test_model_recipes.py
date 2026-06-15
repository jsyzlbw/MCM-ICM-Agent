from mcm_agent.core.model_recipes import MODEL_RECIPES, recipe_for_problem_type, route_recipe


def test_recipe_library_contains_high_value_contest_archetypes() -> None:
    assert "classification" in MODEL_RECIPES
    assert "clustering" in MODEL_RECIPES
    assert "queuing" in MODEL_RECIPES


def test_route_recipe_exposes_solver_contract() -> None:
    recipe = route_recipe("classification_model")

    assert recipe.route_id == "classification_model"
    assert recipe.solver_module == "mcm_agent.solver_modules.classification"
    assert "classification_accuracy" in recipe.metrics
    assert recipe.column_bindings["label_column"] == ""


def test_recipe_lookup_by_problem_type() -> None:
    recipe = recipe_for_problem_type("queuing")

    assert recipe.route_id == "queuing_service_model"
    assert "arrival rate" in " ".join(recipe.data_needs)
