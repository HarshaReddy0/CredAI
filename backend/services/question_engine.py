"""Decides which question to ask next, honouring conditional fields
(e.g. employer name is only asked to salaried / business applicants)."""
from backend.services.form_schema import FIELD_MAP, FIELDS, is_applicable


class QuestionEngine:
    def applicable_fields(self, keys, answers):
        keys = keys or [f["key"] for f in FIELDS]
        return [FIELD_MAP[k] for k in keys if k in FIELD_MAP and is_applicable(FIELD_MAP[k], answers)]

    def get_next_question(self, keys, answers, language="en", skipped=None):
        skipped = set(skipped or [])
        fields = self.applicable_fields(keys, answers)
        for f in fields:
            if f["key"] in answers or f["key"] in skipped:
                continue
            return {
                "completed": False,
                "field_key": f["key"],
                "question_text": f["q"].get(language) or f["q"]["en"],
                "type": f["type"],
                "label": f["label"].get(language) or f["label"]["en"],
                "required": f["required"],
                "progress": self.progress(fields, answers, skipped),
            }
        return {"completed": True, "progress": self.progress(fields, answers, skipped)}

    @staticmethod
    def progress(fields, answers, skipped):
        done = sum(1 for f in fields if f["key"] in answers or f["key"] in skipped)
        return {"total": len(fields), "answered": done, "percent": round(done / max(len(fields), 1) * 100)}
