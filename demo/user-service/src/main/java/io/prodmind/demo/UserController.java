package io.prodmind.demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/users")
public class UserController {
    private final JdbcTemplate jdbcTemplate;

    public UserController(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @PostMapping
    public ResponseEntity<Map<String, Object>> createUser(@RequestBody CreateUserRequest request) {
        jdbcTemplate.update(
                "insert into demo_user(name, phone) values (?, ?)",
                request.name(),
                request.phone()
        );

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("message", "User created");
        body.put("name", request.name());
        body.put("phone", request.phone());
        return ResponseEntity.status(HttpStatus.CREATED).body(body);
    }

    public record CreateUserRequest(String name, String phone) {
    }
}
