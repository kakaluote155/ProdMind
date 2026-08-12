package io.prodmind.demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

import java.util.Map;

@RestController
@RequestMapping("/api/journey")
public class JourneyController {
    private final RestClient slowService;

    public JourneyController(
            @Value("${demo.slow-service-url:http://demo-slow-service:8090}") String slowServiceUrl
    ) {
        this.slowService = RestClient.builder()
                .baseUrl(slowServiceUrl)
                .build();
    }

    @PostMapping("/slow")
    public ResponseEntity<Map<String, Object>> slowJourney() {
        slowService.post()
                .uri("/api/dependency/slow")
                .retrieve()
                .toBodilessEntity();

        return ResponseEntity.ok(Map.of(
                "message", "Journey completed"
        ));
    }
}
