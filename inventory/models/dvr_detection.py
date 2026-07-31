from ..extensions import db


class DvrDetection(db.Model):
    """Detecção inteligente (SMD) reportada por um DVR: humano ou veículo.

    Quem classifica é o próprio DVR — o InvenSync só escuta o fluxo de eventos
    (`services/dvr_events.py`) e guarda o histórico. O retângulo vem na escala
    0-8191 do fabricante; `rect_*_pct` já converte para % da imagem, que é o que
    o navegador precisa para desenhar a caixa sobre o vídeo.
    """
    __tablename__ = "dvr_detection"

    id = db.Column(db.Integer, primary_key=True)
    dvr_id = db.Column(db.Integer, db.ForeignKey("dvr.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    channel = db.Column(db.Integer, nullable=False, index=True)

    # human | vehicle
    object_type = db.Column(db.String(12), nullable=False, index=True)

    # Retângulo do objeto na escala do DVR (0-8191). Nulo se o evento não trouxe.
    rect_x1 = db.Column(db.Integer, nullable=True)
    rect_y1 = db.Column(db.Integer, nullable=True)
    rect_x2 = db.Column(db.Integer, nullable=True)
    rect_y2 = db.Column(db.Integer, nullable=True)

    started_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now(), index=True)
    ended_at = db.Column(db.DateTime, nullable=True)   # preenchido no evento "Stop"

    dvr = db.relationship("Dvr", backref=db.backref("detections", lazy="dynamic",
                                                    cascade="all, delete-orphan"))

    # Espaço de coordenadas das caixas — MEDIDO nos eventos reais, não suposto:
    # em 17 amostras os valores foram de 0 a 1021 (X máx 972, Y máx 1021), e só
    # dividindo por 1024 as proporções fecham (pessoa alta e estreita, veículo
    # quadrado). Não confunda com o SizeFilter da configuração, que usa 0-8191.
    ESCALA = 1024.0

    @property
    def rect_pct(self):
        """(esquerda, topo, largura, altura) em % — pronto para posicionar em CSS."""
        if self.rect_x1 is None:
            return None
        x1, y1 = self.rect_x1 / self.ESCALA, self.rect_y1 / self.ESCALA
        x2, y2 = self.rect_x2 / self.ESCALA, self.rect_y2 / self.ESCALA
        return (round(x1 * 100, 2), round(y1 * 100, 2),
                round(max(0.0, x2 - x1) * 100, 2), round(max(0.0, y2 - y1) * 100, 2))

    @property
    def rotulo(self) -> str:
        return {"human": "Humano", "vehicle": "Veículo"}.get(self.object_type, self.object_type)

    def __repr__(self) -> str:
        return (f"<DvrDetection dvr={self.dvr_id} ch={self.channel} "
                f"{self.object_type} {self.started_at}>")
