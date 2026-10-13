from gbmap import model
from gbmap.model import FieldMap, TableMap


COLS = {"ST_RESULT_USR": {"LAB_METHOD", "RESULT"}, "GB_PROJECT": {"DESCRIPTION"}}


def test_resolve_table_falls_back_to_default():
    assert model.resolve_table("ST_RESULT", []) == "ST_RESULT"
    assert model.resolve_table("st_result", [TableMap("ST_RESULT", "ST_RESULT_USR")]) == "ST_RESULT_USR"


def test_resolve_field_falls_back_to_default():
    assert model.resolve_field("ST_RESULT", "METHOD", []) == "METHOD"
    maps = [FieldMap("ST_RESULT", "METHOD", "LAB_METHOD")]
    assert model.resolve_field("ST_RESULT", "METHOD", maps) == "LAB_METHOD"


def test_field_map_without_table_map_is_error():
    issues = model.validate([], [FieldMap("ST_RESULT", "METHOD", "LAB_METHOD")], COLS)
    assert model.has_errors(issues)
    assert any("tabela correspondente" in i.message for i in issues)


def test_missing_user_table_and_column_are_errors():
    issues = model.validate(
        [TableMap("ST_RESULT", "NAO_EXISTE")],
        [],
        COLS,
    )
    assert model.has_errors(issues)


def test_column_check_is_case_insensitive():
    tm = [TableMap("ST_RESULT", "ST_RESULT_USR")]
    fm = [FieldMap("ST_RESULT", "METHOD", "lab_method")]
    assert not model.has_errors(model.validate(tm, fm, COLS))


def test_missing_column_is_error():
    tm = [TableMap("ST_RESULT", "ST_RESULT_USR")]
    fm = [FieldMap("ST_RESULT", "METHOD", "NOPE")]
    assert model.has_errors(model.validate(tm, fm, COLS))


def test_duplicate_field_map_is_error():
    tm = [TableMap("ST_RESULT", "ST_RESULT_USR")]
    fm = [FieldMap("ST_RESULT", "METHOD", "LAB_METHOD"), FieldMap("ST_RESULT", "METHOD", "LAB_METHOD")]
    assert model.has_errors(model.validate(tm, fm, COLS))


def test_qaqc_correction_is_warning_not_error():
    tm = [TableMap("ST_XS_STANDARD", "ST_XS_STANDARD_USR")]
    cols = {"ST_XS_STANDARD_USR": {"QAQC_TYPE"}}
    fm = [FieldMap("ST_XS_STANDARD", "QAQC_TYPE", "QAQC_TYPE")]
    issues = model.validate(tm, fm, cols)
    assert not model.has_errors(issues)
    assert any(i.level == model.WARNING and "QC_TYPE" in i.message for i in issues)


def test_redundant_mapping_is_warning():
    tm = [TableMap("GB_PROJECT", "GB_PROJECT")]
    issues = model.validate(tm, [], COLS)
    assert not model.has_errors(issues)
    assert any("redundante" in i.message for i in issues)
