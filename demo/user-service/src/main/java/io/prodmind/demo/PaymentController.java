package io.prodmind.demo;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

import java.util.Map;

@RestController
@RequestMapping("/api/payments")
public class PaymentController {
    private final RestClient unavailableDependency = RestClient.builder()
            .baseUrl("http://127.0.0.1:65530")
            .build();

    @PostMapping("/charge")
    public ResponseEntity<Map<String, Object>> charge() {
        // Port 65530 intentionally has no listener inside the demo container.
        // Spring throws a ResourceAccessException/ConnectException and the
        // global FailureHandler converts it to the same generic customer error.
        unavailableDependency.post()
                .uri("/charge")
                .retrieve()
                .toBodilessEntity();

        return ResponseEntity.ok(Map.of("message", "Payment charged"));
    }
}
