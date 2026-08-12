package io.prodmind.demo;

import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/users")
public class UserController {
    private static final Logger log = LoggerFactory.getLogger(UserController.class);

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

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, Object>> handleFailure(Exception exception) {
        Span span = Span.current();
        String traceId = currentTraceId(span);
        String rootMessage = rootMessage(exception);

        // Record structured evidence on the active request span. The demo does
        // this explicitly so the RCA remains deterministic even if log delivery
        // is delayed or temporarily unavailable.
        span.setStatus(StatusCode.ERROR, "create_user_failed");
        span.recordException(exception);
        span.addEvent(
                "prodmind.demo.failure",
                Attributes.of(
                        AttributeKey.stringKey("exception.type"), exception.getClass().getName(),
                        AttributeKey.stringKey("exception.message"), rootMessage
                )
        );

        // The demo intentionally returns a generic message to the customer while
        // preserving the technical evidence in telemetry for ProdMind to inspect.
        log.error(
                "trace_id={} operation=create_user failed exception={} root_message={}",
                traceId,
                exception.getClass().getName(),
                rootMessage,
                exception
        );

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("message", "Operation failed");
        body.put("traceId", traceId);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(body);
    }

    private static String currentTraceId(Span span) {
        var context = span.getSpanContext();
        return context.isValid() ? context.getTraceId() : "unavailable";
    }

    private static String rootMessage(Throwable throwable) {
        Throwable current = throwable;
        while (current.getCause() != null) {
            current = current.getCause();
        }
        return current.getClass().getName() + ": " + String.valueOf(current.getMessage());
    }

    public record CreateUserRequest(String name, String phone) {
    }
}
