package io.prodmind.demo;

import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/reports")
public class ReportController {
    private final JdbcTemplate jdbcTemplate;

    public ReportController(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @PostMapping("/slow")
    public ResponseEntity<Map<String, Object>> generateSlowReport() {
        // This operation intentionally succeeds after spending most of the request
        // inside PostgreSQL. It gives ProdMind a real HTTP-200 latency incident.
        jdbcTemplate.execute("select pg_sleep(3)");

        return ResponseEntity.ok(Map.of(
                "message", "Report generated",
                "rows", 42
        ));
    }
}
