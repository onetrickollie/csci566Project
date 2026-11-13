"""Behavior cloning, trajectory augmentation, and DAgger for the coordinator.

The policy is a small MLP over the encoded observation with an action mask.
All three training regimes share the same model and trainer; they differ
only in which (state, expert action) pairs end up in the dataset:

* BC       : states visited by the expert itself.
* Augment  : expert rollouts with one injected mistake per episode; the
             expert's recovery actions are recorded.
* DAgger   : states visited by the current policy (mixed with the expert
             with probability beta), relabeled by the expert.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import numpy as np
import torch
from torch import nn

from taskflow.env.episode import run_episode
from taskflow.env.state import A, ACTIONS, LOCAL_ACTION, TERMINAL
from taskflow.learning.encode import action_mask, encode


class MLP(nn.Module):
    def __init__(self, n_in: int, n_out: int = len(ACTIONS), hidden: int = 256):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(n_in, hidden), nn.ReLU(), nn.Linear(hidden, hidden),
                                 nn.ReLU(), nn.Linear(hidden, n_out))

    def forward(self, x):
        return self.net(x)


class LearnedPolicy:
    def __init__(self, model: MLP, name: str = "learned"):
        self.model, self.name = model.eval(), name

    @torch.no_grad()
    def act(self, env) -> str:
        x = torch.from_numpy(encode(env)).unsqueeze(0)
        logits = self.model(x)[0].numpy()
        logits[~action_mask(env)] = -1e9
        return ACTIONS[int(logits.argmax())]


@dataclass
class Data:
    X: list
    y: list

    def extend(self, traj: list[dict]) -> None:
        for t in traj:
            self.X.append(t["state"])
            self.y.append(A[t["expert_action"]])

    def __len__(self):
        return len(self.y)


def collect(episodes, Q, policy, expert, beta: float, seed: int, inject_rate: float = 0.0) -> Data:
    rng = random.Random(seed)
    data = Data([], [])
    for i, ep in enumerate(episodes):
        inject = None
        if inject_rate and rng.random() < inject_rate:
            t = rng.randrange(len(ep.turns))
            inject = {"turn": t, "step": rng.choice([0, 0, 1, 2]), "action": _random_mistake(rng)}
        r = run_episode(ep, Q[ep.qid], policy, seed=seed * 100003 + i, expert=expert, beta=beta,
                        record=True, inject=inject, encoder=encode)
        data.extend(r.trajectory)
    return data


def _random_mistake(rng: random.Random) -> str:
    return rng.choice(list(LOCAL_ACTION.values()) + ["REPLAN_GLOBAL", "SEARCH_ACCOMMODATION",
                                                     "SEARCH_TRANSPORTATION", "SEARCH_ACTIVITY_DINING"])


def train(data: Data, seed: int, epochs: int = 40, lr: float = 1e-3, hidden: int = 256,
          model: MLP | None = None) -> tuple[MLP, dict]:
    torch.manual_seed(seed)
    X = torch.from_numpy(np.stack(data.X))
    y = torch.tensor(data.y)
    model = model or MLP(X.shape[1], hidden=hidden)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    # Class weights keep rare actions (ASK, global replans) from being ignored.
    counts = torch.bincount(y, minlength=len(ACTIONS)).float()
    w = (counts.sum() / (counts + 1.0)).sqrt().clamp(max=10.0)
    w = w / w.mean()
    lossf = nn.CrossEntropyLoss(weight=w)
    g = torch.Generator().manual_seed(seed)
    model.train()
    for _ in range(epochs):
        perm = torch.randperm(len(y), generator=g)
        for b in range(0, len(y), 256):
            idx = perm[b:b + 256]
            loss = lossf(model(X[idx]), y[idx])
            opt.zero_grad()
            loss.backward()
            opt.step()
    model.eval()
    with torch.no_grad():
        acc = (model(X).argmax(1) == y).float().mean().item()
    return model, {"n": len(y), "train_acc": acc}


def dagger(train_eps, Q, expert, seed: int, iters: int = 3, betas=(0.5, 0.25, 0.0),
           init: Data | None = None, epochs: int = 40, log=print):
    data = Data(list(init.X), list(init.y)) if init else collect(train_eps, Q, expert, expert, 0.0, seed)
    model, info = train(data, seed, epochs=epochs)
    history = [{"iter": 0, **info}]
    log(f"  dagger iter 0: {info}")
    for i in range(iters):
        pol = LearnedPolicy(model)
        new = collect(train_eps, Q, pol, expert, betas[min(i, len(betas) - 1)], seed + 17 * (i + 1))
        data.X += new.X
        data.y += new.y
        model, info = train(data, seed, epochs=epochs)
        history.append({"iter": i + 1, "added": len(new), **info})
        log(f"  dagger iter {i + 1}: {history[-1]}")
        yield i + 1, model, history


def save_model(model: MLP, path) -> None:
    torch.save({"state_dict": model.state_dict(), "n_in": model.net[0].in_features,
                "hidden": model.net[0].out_features}, path)


def load_model(path) -> MLP:
    ck = torch.load(path, weights_only=True)
    m = MLP(ck["n_in"], hidden=ck["hidden"])
    m.load_state_dict(ck["state_dict"])
    return m.eval()


__all__ = ["MLP", "LearnedPolicy", "Data", "collect", "train", "dagger", "save_model",
           "load_model", "TERMINAL"]
