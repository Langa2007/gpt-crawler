"""Small PyTorch GPT prototype for training on local Scrapper knowledge.

This is intentionally separate from the production provider registry. It is a
training and experimentation tool that can later become a local model
provider once its quality and resource requirements are understood.

Examples:
    python -m python_ai.gpt.gpt --steps 1000
    python -m python_ai.gpt.gpt --corpus path/to/notes.txt --steps 2000
    python -m python_ai.gpt.gpt --checkpoint artifacts/scrapper-gpt.pt
"""

from __future__ import annotations

import argparse
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import sentencepiece as spm
import torch
import torch.nn as nn
from torch.nn import functional as F


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = Path(__file__).with_name("knowledge.txt")
DEFAULT_ARTIFACTS = ROOT / "artifacts" / "gpt"


@dataclass(frozen=True)
class ModelConfig:
    vocab_size: int
    block_size: int = 128
    n_embd: int = 192
    n_head: int = 6
    n_layer: int = 6
    dropout: float = 0.1


class CausalSelfAttention(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        if config.n_embd % config.n_head != 0:
            raise ValueError("n_embd must be divisible by n_head")
        self.attn = nn.Linear(config.n_embd, 3 * config.n_embd)
        self.proj = nn.Linear(config.n_embd, config.n_embd)
        self.dropout = nn.Dropout(config.dropout)
        self.register_buffer(
            "causal_mask",
            torch.tril(torch.ones(config.block_size, config.block_size)).view(
                1, 1, config.block_size, config.block_size
            ),
        )
        self.n_head = config.n_head

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batch, steps, channels = x.shape
        query, key, value = self.attn(x).split(channels, dim=2)
        head_size = channels // self.n_head
        query = query.view(batch, steps, self.n_head, head_size).transpose(1, 2)
        key = key.view(batch, steps, self.n_head, head_size).transpose(1, 2)
        value = value.view(batch, steps, self.n_head, head_size).transpose(1, 2)
        weights = query @ key.transpose(-2, -1) / math.sqrt(head_size)
        weights = weights.masked_fill(self.causal_mask[:, :, :steps, :steps] == 0, float("-inf"))
        weights = F.softmax(weights, dim=-1)
        weights = self.dropout(weights)
        output = weights @ value
        output = output.transpose(1, 2).contiguous().view(batch, steps, channels)
        return self.dropout(self.proj(output))


class TransformerBlock(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.norm1 = nn.LayerNorm(config.n_embd)
        self.attention = CausalSelfAttention(config)
        self.norm2 = nn.LayerNorm(config.n_embd)
        self.feed_forward = nn.Sequential(
            nn.Linear(config.n_embd, 4 * config.n_embd),
            nn.GELU(),
            nn.Linear(4 * config.n_embd, config.n_embd),
            nn.Dropout(config.dropout),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.attention(self.norm1(x))
        return x + self.feed_forward(self.norm2(x))


class GPTLanguageModel(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.config = config
        self.token_embedding = nn.Embedding(config.vocab_size, config.n_embd)
        self.position_embedding = nn.Embedding(config.block_size, config.n_embd)
        self.blocks = nn.Sequential(*(TransformerBlock(config) for _ in range(config.n_layer)))
        self.norm = nn.LayerNorm(config.n_embd)
        self.lm_head = nn.Linear(config.n_embd, config.vocab_size, bias=False)
        self.lm_head.weight = self.token_embedding.weight
        self.apply(self._init_weights)

    @staticmethod
    def _init_weights(module: nn.Module) -> None:
        if isinstance(module, (nn.Linear, nn.Embedding)):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if isinstance(module, nn.Linear) and module.bias is not None:
                nn.init.zeros_(module.bias)

    def forward(
        self, token_ids: torch.Tensor, targets: torch.Tensor | None = None
    ) -> Tuple[torch.Tensor, torch.Tensor | None]:
        _, steps = token_ids.shape
        if steps > self.config.block_size:
            raise ValueError("input length exceeds the configured block size")
        positions = torch.arange(steps, device=token_ids.device)
        hidden = self.token_embedding(token_ids) + self.position_embedding(positions)
        hidden = self.blocks(hidden)
        logits = self.lm_head(self.norm(hidden))
        loss = None
        if targets is not None:
            loss = F.cross_entropy(logits.reshape(-1, logits.size(-1)), targets.reshape(-1))
        return logits, loss

    @torch.no_grad()
    def generate(
        self, token_ids: torch.Tensor, max_new_tokens: int, temperature: float = 0.8
    ) -> torch.Tensor:
        self.eval()
        for _ in range(max_new_tokens):
            context = token_ids[:, -self.config.block_size :]
            logits, _ = self(context)
            probabilities = F.softmax(logits[:, -1, :] / max(temperature, 1e-5), dim=-1)
            next_token = torch.multinomial(probabilities, num_samples=1)
            token_ids = torch.cat((token_ids, next_token), dim=1)
        return token_ids


def train_tokenizer(corpus: Path, model_path: Path, vocab_size: int) -> spm.SentencePieceProcessor:
    model_path.parent.mkdir(parents=True, exist_ok=True)
    if not model_path.exists():
        spm.SentencePieceTrainer.train(
            input=str(corpus),
            model_prefix=str(model_path.with_suffix("")),
            vocab_size=vocab_size,
            model_type="unigram",
            character_coverage=1.0,
            hard_vocab_limit=False,
            pad_id=0,
            unk_id=1,
            bos_id=2,
            eos_id=3,
        )
    return spm.SentencePieceProcessor(model_file=str(model_path))


def load_tokens(tokenizer: spm.SentencePieceProcessor, corpus: Path) -> torch.Tensor:
    tokens = tokenizer.encode(corpus.read_text(encoding="utf-8"), out_type=int)
    if len(tokens) < 3:
        raise ValueError(f"Corpus must produce at least three tokens: {corpus}")
    return torch.tensor(tokens, dtype=torch.long)


def batches(
    data: torch.Tensor, split: str, block_size: int, batch_size: int, device: torch.device
) -> Tuple[torch.Tensor, torch.Tensor]:
    split_at = max(1, int(len(data) * 0.9))
    source = data[:split_at] if split == "train" else data[split_at:]
    if len(source) <= block_size:
        source = data
    starts = torch.randint(len(source) - block_size, (batch_size,))
    inputs = torch.stack([source[start : start + block_size] for start in starts])
    targets = torch.stack([source[start + 1 : start + block_size + 1] for start in starts])
    return inputs.to(device), targets.to(device)


@torch.no_grad()
def estimate_loss(
    model: GPTLanguageModel, data: torch.Tensor, config: ModelConfig, device: torch.device
) -> Dict[str, float]:
    model.eval()
    result: Dict[str, float] = {}
    for split in ("train", "val"):
        losses = []
        for _ in range(10):
            inputs, targets = batches(data, split, config.block_size, 4, device)
            _, loss = model(inputs, targets)
            if loss is not None:
                losses.append(loss.item())
        result[split] = sum(losses) / len(losses)
    model.train()
    return result


def train(args: argparse.Namespace) -> None:
    torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    corpus = Path(args.corpus)
    artifacts = Path(args.artifacts)
    tokenizer = train_tokenizer(corpus, artifacts / "tokenizer.model", args.vocab_size)
    data = load_tokens(tokenizer, corpus)
    config = ModelConfig(vocab_size=tokenizer.get_piece_size(), block_size=args.block_size)
    model = GPTLanguageModel(config).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)

    for step in range(args.steps):
        if step % args.eval_interval == 0 or step == args.steps - 1:
            losses = estimate_loss(model, data, config, device)
            print(f"step {step}: train loss {losses['train']:.4f}, val loss {losses['val']:.4f}")
        inputs, targets = batches(data, "train", config.block_size, args.batch_size, device)
        _, loss = model(inputs, targets)
        if loss is None:
            raise RuntimeError("training batch did not produce a loss")
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

    artifacts.mkdir(parents=True, exist_ok=True)
    checkpoint = artifacts / "model.pt"
    torch.save({"config": asdict(config), "model": model.state_dict()}, checkpoint)
    prompt_ids = torch.tensor([tokenizer.encode(args.prompt, out_type=int)], device=device)
    generated = model.generate(prompt_ids, args.max_new_tokens, args.temperature)
    print(f"device: {device}; checkpoint: {checkpoint}")
    print(tokenizer.decode(generated[0].tolist()))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--eval-interval", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--block-size", type=int, default=128)
    parser.add_argument("--vocab-size", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--max-new-tokens", type=int, default=160)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--prompt", default="Scrapper uses")
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--cpu", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    train(parse_args())
