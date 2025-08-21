package com.example.payments_api.model;


import java.time.OffsetDateTime;

public record PaymentResponse(
        String paymentId,
        String status,          // APPROVED | DECLINED | PENDING
        Double amount,
        String currency,
        OffsetDateTime createdAt
) {}
