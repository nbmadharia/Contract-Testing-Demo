package com.example.payments_api.model;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record PaymentRequest(
        @NotNull @Min(1) Double amount,
        @NotBlank String currency,
        @NotBlank String merchantId,
        String description
) {}
