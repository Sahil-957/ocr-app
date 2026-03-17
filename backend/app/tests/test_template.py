from app.services.template_config import load_template


def test_template_contains_core_fields():
    template = load_template()
    for field in ["date", "customer", "quality", "total_price", "target_price"]:
        assert field in template["fields"]
