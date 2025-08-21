package com.example.payments_api.controller;

import com.example.payments_api.model.ErrorResponse;
import com.example.payments_api.model.PaymentRequest;
import com.example.payments_api.model.PaymentResponse;
import com.example.payments_api.service.PaymentService;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.net.URI;

@RestController
@RequestMapping("/payments")
public class PaymentController {

    private final PaymentService service = new PaymentService();

    @PostMapping
    public ResponseEntity<?> create(
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @Valid @RequestBody PaymentRequest request) {

        if (request.amount() == null || request.amount() < 0.01)
            return ResponseEntity.badRequest().body(new ErrorResponse("BAD_REQUEST", "Invalid amount"));

        PaymentResponse saved = service.create(idempotencyKey, request);
        return ResponseEntity
                .created(URI.create("/payments/" + saved.paymentId()))
                .body(saved);
    }

    @GetMapping("/{id}")
    public ResponseEntity<?> get(@PathVariable String id) {
        PaymentResponse resp = service.get(id);
        if (resp == null) {
            return ResponseEntity.status(404)
                    .body(new ErrorResponse("NOT_FOUND", "Payment not found"));
        }
        return ResponseEntity.ok(resp);
    }
}
