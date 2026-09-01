"""
DynamicDeepHit architecture - must match training exactly.
"""
from __future__ import annotations

import torch
import torch.nn as nn


class DynamicDeepHit(nn.Module):
    """
    Dynamic DeepHit model with (K+1) bin architecture for survival analysis.

    The model outputs a probability mass function (PMF) over K+1 bins, where:
    - Bins 0 to K-1 represent failure intervals [t_k, t_{k+1})
    - Bin K represents survival past the maximum observation horizon (T > t_max)

    The PMF sums to 1.0 across all K+1 bins.
    """

    def __init__(self, n_features: int, hidden_dim: int = 32, n_time_bins: int = 20, dropout: float = 0.2):
        """
        Args:
            n_features: Number of input features per timestep
            hidden_dim: GRU hidden dimension
            n_time_bins: Number of discrete time intervals K (model outputs K+1 bins)
            dropout: Dropout probability
        """
        super().__init__()
        self.n_time_bins = n_time_bins
        self.rnn = nn.GRU(n_features, hidden_dim, batch_first=True)
        self.attn = nn.Linear(hidden_dim, 1)
        self.dropout = nn.Dropout(dropout)
        # Output dimension is n_time_bins + 1 (K+1 bins: K failure intervals + 1 survival tail)
        self.risk_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, n_time_bins + 1),
        )

    def forward(self, X: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        """
        Forward pass returning PMF over K+1 bins.

        Args:
            X: Input tensor of shape [Batch, Seq_Len, n_features]
            mask: Binary mask of shape [Batch, Seq_Len] (1=valid, 0=padded)

        Returns:
            pmf: Probability mass function of shape [Batch, n_time_bins + 1]
                 Summing to 1.0 across the last dimension.
        """
        lengths = mask.sum(dim=1).long().clamp(min=1)
        packed = nn.utils.rnn.pack_padded_sequence(
            X, lengths.cpu(), batch_first=True, enforce_sorted=False
        )
        packed_out, _ = self.rnn(packed)
        h_all, _ = nn.utils.rnn.pad_packed_sequence(packed_out, batch_first=True)

        scores = self.attn(h_all).squeeze(-1)
        pad_mask = mask[:, :h_all.shape[1]] == 0
        scores = scores.masked_fill(pad_mask, torch.finfo(scores.dtype).min)
        weights = torch.softmax(scores, dim=1)
        weights = weights * (~pad_mask).float()
        weights = weights / weights.sum(dim=1, keepdim=True).clamp_min(1e-8)
        h_pooled = (weights.unsqueeze(-1) * h_all).sum(dim=1)

        logits = self.risk_head(self.dropout(h_pooled))
        pmf = torch.softmax(logits, dim=1)  # Shape: [Batch, K+1]
        pmf = pmf.clamp_min(1e-8)
        return pmf / pmf.sum(dim=1, keepdim=True).clamp_min(1e-8)