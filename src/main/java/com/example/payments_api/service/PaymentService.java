package com.example.payments_api.service;


import com.example.payments_api.model.PaymentRequest;
import com.example.payments_api.model.PaymentResponse;

import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public class PaymentService {

    // idempotencyKey -> paymentId
    private final Map<String, String> idempotencyMap = new ConcurrentHashMap<>();
    // paymentId -> response
    private final Map<String, PaymentResponse> store = new ConcurrentHashMap<>();

    public synchronized PaymentResponse create(String idempotencyKey, PaymentRequest req) {
        if (idempotencyMap.containsKey(idempotencyKey)) {
            return store.get(idempotencyMap.get(idempotencyKey));
        }
        // naïve business rule (just for demo)
        String status = (req.amount() <= 50000.00) ? "APPROVED" : "DECLINED";

        String paymentId = "p-" + UUID.randomUUID();
        PaymentResponse resp = new PaymentResponse(
                paymentId, status, req.amount(), req.currency(), OffsetDateTime.now());

        idempotencyMap.put(idempotencyKey, paymentId);
        store.put(paymentId, resp);
        return resp;
    }

    public PaymentResponse get(String id) {
        return store.get(id);
    }
}
