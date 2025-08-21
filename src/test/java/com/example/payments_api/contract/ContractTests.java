package com.example.payments_api.contract;

import io.specmatic.test.SpecmaticContractTest;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.springframework.boot.SpringApplication;
import org.springframework.context.ConfigurableApplicationContext;

// Change this import if your main app class lives elsewhere
import com.example.payments_api.PaymentsApiApplication;

public class ContractTests implements SpecmaticContractTest {
    private static ConfigurableApplicationContext context;

    // Optional: exclude any internal endpoints from contract runs
    // Example syntax: "'/internal/metrics' OR PATH STARTS WITH '/actuator'"
    private static final String EXCLUDED_ENDPOINTS = ""; // keep empty for now

    @BeforeAll
    public static void setUp() {
        // Where your Spring Boot app will run (we’ll start it right here)
        System.setProperty("host", "localhost");
        System.setProperty("port", "8080");

        // Point Specmatic to your OpenAPI (so it doesn’t rely only on specmatic.yaml discovery)
        System.setProperty("contractPaths", "src/main/resources/openapi/simple-payments.yaml");

        // (Optional) Turn on Specmatic's generative tests in addition to example-based ones
        System.setProperty("SPECMATIC_GENERATIVE_TESTS", "false");
        System.setProperty("SPECMATIC_TEST_PARALLELISM", "auto");

        // (Optional) filter out paths if needed
        if (!EXCLUDED_ENDPOINTS.isBlank()) {
            System.setProperty("filter", String.format("PATH!=%s", EXCLUDED_ENDPOINTS));
        }

        // Start your Spring Boot app for the duration of the tests
        context = SpringApplication.run(PaymentsApiApplication.class);
    }

    @AfterAll
    public static void tearDown() {
        if (context != null) context.close();
    }
}
