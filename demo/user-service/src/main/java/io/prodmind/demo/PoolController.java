package io.prodmind.demo;

import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.sql.PreparedStatement;
import java.util.Map;

@RestController
@RequestMapping("/api/pool")
public class PoolController {
    private final JdbcTemplate jdbcTemplate;

    public PoolController(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @PostMapping("/hold")
    public ResponseEntity<Map<String, Object>> holdConnection(
            @RequestParam(defaultValue = "8") int seconds
    ) {
        int holdSeconds = Math.max(1, Math.min(seconds, 15));

        jdbcTemplate.execute((ConnectionCallback<Void>) connection -> {
            try (PreparedStatement statement = connection.prepareStatement("select pg_sleep(?)")) {
                statement.setInt(1, holdSeconds);
                statement.execute();
            }
            return null;
        });

        return ResponseEntity.ok(Map.of(
                "message", "Connection released",
                "seconds", holdSeconds
        ));
    }

    @PostMapping("/probe")
    public ResponseEntity<Map<String, Object>> probePool() {
        Integer value = jdbcTemplate.queryForObject("select 1", Integer.class);
        return ResponseEntity.ok(Map.of(
                "message", "Database available",
                "value", value
        ));
    }
}
