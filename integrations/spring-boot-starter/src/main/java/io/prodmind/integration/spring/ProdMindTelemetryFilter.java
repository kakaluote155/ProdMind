package io.prodmind.integration.spring;

import io.opentelemetry.api.trace.Span;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

public final class ProdMindTelemetryFilter extends OncePerRequestFilter {
    public static final String PROJECT_ATTRIBUTE = "prodmind.project.id";

    private final String projectId;

    ProdMindTelemetryFilter(String projectId) {
        this.projectId = projectId;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        Span.current().setAttribute(PROJECT_ATTRIBUTE, projectId);
        filterChain.doFilter(request, response);
    }
}
