package io.prodmind.demo;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/dependency")
public class SlowDependencyController {

    @PostMapping("/slow")
    public ResponseEntity<Map<String, Object>> slowDependency() {
        try {
            Thread.sleep(2500);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Slow dependency demo was interrupted", exception);
        }

        return ResponseEntity.ok(Map.of(
                "message", "Downstream work completed"
        ));
    }
}
