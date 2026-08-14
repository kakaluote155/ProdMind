package io.prodmind.integration.spring;

import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.export.SimpleSpanProcessor;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ProdMindTelemetryFilterTest {
    @Test
    void tagsCurrentSpanFromServerConfigurationOnly() throws Exception {
        InMemorySpanExporter exporter = InMemorySpanExporter.create();
        SdkTracerProvider provider = SdkTracerProvider.builder()
                .addSpanProcessor(SimpleSpanProcessor.create(exporter))
                .build();
        Tracer tracer = provider.get("test");
        ProdMindTelemetryFilter filter = new ProdMindTelemetryFilter("project-a");
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-ProdMind-Project", "attacker-project");

        Span span = tracer.spanBuilder("request").startSpan();
        try (Scope ignored = span.makeCurrent()) {
            filter.doFilter(request, new MockHttpServletResponse(), new MockFilterChain());
        } finally {
            span.end();
        }

        assertThat(exporter.getFinishedSpanItems()).hasSize(1);
        assertThat(exporter.getFinishedSpanItems().getFirst().getAttributes()
                .get(io.opentelemetry.api.common.AttributeKey.stringKey(
                        ProdMindTelemetryFilter.PROJECT_ATTRIBUTE)))
                .isEqualTo("project-a");
        provider.close();
    }

    @Test
    void rejectsMissingOrInvalidProjectConfiguration() {
        ProdMindProperties missing = new ProdMindProperties();
        assertThatThrownBy(missing::requireProjectId)
                .isInstanceOf(IllegalStateException.class);

        ProdMindProperties invalid = new ProdMindProperties();
        invalid.setProjectId("bad project");
        assertThatThrownBy(invalid::requireProjectId)
                .isInstanceOf(IllegalStateException.class);
    }
}
