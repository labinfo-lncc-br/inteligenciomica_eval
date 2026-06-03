"""CohenKappaAdapter — implementação de KappaCalculatorPort via sklearn.

``sklearn`` é tratado como biblioteca de infraestrutura de ML e fica APENAS neste
módulo (Nota de operacionalização M6, item 5). Proibido em domain/ e application/.
"""

from __future__ import annotations

from collections.abc import Sequence


class CohenKappaAdapter:
    """Implementa KappaCalculatorPort usando sklearn.metrics.cohen_kappa_score.

    A importação de ``sklearn`` é lazy (dentro do método) para evitar
    import-time side-effects e manter compatibilidade com o import-linter.
    """

    def compute(
        self,
        y_true: Sequence[int],
        y_pred: Sequence[int],
    ) -> float:
        """Calcula Cohen's κ entre dois vetores de rótulos binários.

        Args:
            y_true: rótulos do anotador humano (referência); valores em {0, 1}.
            y_pred: rótulos do juiz LLM binarizados; valores em {0, 1}.

        Returns:
            Coeficiente kappa de Cohen em [-1, 1].
        """
        from sklearn.metrics import cohen_kappa_score

        return float(cohen_kappa_score(list(y_true), list(y_pred)))
