def test_page_slug_for_name_bo_hang_va_bien_the() -> None:
    from src.agents.domain.catalog_browse import page_slug_for_name

    assert page_slug_for_name("VinFast VF 8 Plus") == "vf-8"
    assert page_slug_for_name("VinFast VF 5") == "vf-5"
    assert page_slug_for_name("VinFast Evo Grand") == ""


def test_page_path_cho_ca_o_to_lan_xe_may() -> None:
    from src.agents.domain.catalog_browse import page_path_for_name

    assert page_path_for_name("VinFast VF 5 All New") == "/vehicles/vf-5"
    assert page_path_for_name("VinFast Vero X Standard") == "/motorbikes/vero-x"
    assert page_path_for_name("VinFast Feliz II Kèm Pin") == "/motorbikes/feliz-ii"
    assert page_path_for_name("VinFast Evo Grand Lite") == "/motorbikes/evo-grand-lite"
    # Mẫu chưa có trang → rỗng, client giữ bản tóm tắt.
    assert page_path_for_name("VinFast Theon S") == ""
