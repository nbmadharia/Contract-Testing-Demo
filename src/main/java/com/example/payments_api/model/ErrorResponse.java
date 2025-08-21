package com.example.payments_api.model;



public record ErrorResponse(
        String code,
        String message
) {}
