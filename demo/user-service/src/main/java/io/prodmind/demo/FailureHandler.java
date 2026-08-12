package io.prodmind.demo;

import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.LinkedHashMap;
import java.util.Map;

@RestControllerAdvice
public class FailureHandler {
    private static final Logger log = LoggerFactory.getLogger(FailureHandler.class);

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, Object>> handleFailure(
            Exception exception,
            HttpServletRequest request
    ) {
        Span span = Span.current();
        String traceId = currentTraceId(span);
        String rootMessage = rootMessage(exception);
        String operation = request.getMethod() + " " + request.getRequestURI();

        span.setStatus(StatusCode.ERROR, "customer_operation_failed");
        span.recordException(exception);
        span.addEvent(
                "prodmind.demo.failure",
                Attributes.of(
                        AttributeKey.stringKey("exception.type"), exception.getClass().getName(),
                        AttributeKey.stringKey("exception.message"), rootMessage,
                        AttributeKey.stringKey("prodmind.operation"), operation
                )
        );

        log.error(
                "trace_id={} operation={} failed exception={} root_message={}",
                traceId,
                operation,
                exception.getClass().getName(),
                rootMessage,
                exception
        );

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("message", "Operation failed");
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
}
