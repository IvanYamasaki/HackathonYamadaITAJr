"""
model.py — Actor-Critic (MLP) em PyTorch para o PPO do v15.

Rede pequena de propósito: a inferência no torneio é um forward numpy
exportado (ver export.py / player_versao_15.py), então o gargalo é a
simulação das partidas (CPU), não a rede. A CUDA acelera o batch de forward/
backward durante o treino.

A política compartilha o tronco com o crítico (value head) — padrão em PPO.
A camada final da política é exportada para numpy no formato esperado pelo
player (tanh nas camadas ocultas, logits na última).
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn


class ActorCritic(nn.Module):
    def __init__(self, feat_dim: int, n_actions: int, hidden=(128, 128)):
        super().__init__()
        self.feat_dim = feat_dim
        self.n_actions = n_actions
        self.hidden = tuple(hidden)

        # Tronco compartilhado (tanh: casa com o forward numpy do player).
        layers = []
        last = feat_dim
        for h in hidden:
            layers += [nn.Linear(last, h), nn.Tanh()]
            last = h
        self.body = nn.Sequential(*layers)
        self.pi_head = nn.Linear(last, n_actions)
        self.v_head = nn.Linear(last, 1)

        self.apply(self._init)
        # Política começa "tímida" (logits pequenos) → exploração suave.
        nn.init.orthogonal_(self.pi_head.weight, gain=0.01)
        nn.init.zeros_(self.pi_head.bias)

    @staticmethod
    def _init(m):
        if isinstance(m, nn.Linear):
            nn.init.orthogonal_(m.weight, gain=np.sqrt(2))
            nn.init.zeros_(m.bias)

    def forward(self, x):
        z = self.body(x)
        return self.pi_head(z), self.v_head(z).squeeze(-1)

    def _masked_logits(self, x, mask):
        logits, value = self.forward(x)
        logits = logits.masked_fill(~mask, -1e9)
        return logits, value

    @torch.no_grad()
    def act(self, x, mask):
        """Amostra ação (treino). Retorna (action, logprob, value)."""
        logits, value = self._masked_logits(x, mask)
        dist = torch.distributions.Categorical(logits=logits)
        a = dist.sample()
        return a, dist.log_prob(a), value

    def evaluate(self, x, mask, actions):
        """Para o update PPO: logprob, entropia e value das ações tomadas."""
        logits, value = self._masked_logits(x, mask)
        dist = torch.distributions.Categorical(logits=logits)
        return dist.log_prob(actions), dist.entropy(), value

    # ── Export para numpy (consumido pelo player_versao_15) ──────────────
    def export_numpy(self) -> dict:
        """Achata tronco + pi_head numa lista de (W, b) para o forward numpy.

        Convenção numpy do player: x @ W + b, tanh entre camadas, logits no
        fim. PyTorch Linear faz x @ W.T + b → exportamos W.T.
        """
        mats = []
        for m in self.body:
            if isinstance(m, nn.Linear):
                mats.append((m.weight.detach().cpu().numpy().T.copy(),
                             m.bias.detach().cpu().numpy().copy()))
        mats.append((self.pi_head.weight.detach().cpu().numpy().T.copy(),
                     self.pi_head.bias.detach().cpu().numpy().copy()))
        out = {"n_layers": np.array(len(mats), dtype=np.int64)}
        for i, (w, b) in enumerate(mats):
            out[f"w{i}"] = w.astype(np.float32)
            out[f"b{i}"] = b.astype(np.float32)
        return out
