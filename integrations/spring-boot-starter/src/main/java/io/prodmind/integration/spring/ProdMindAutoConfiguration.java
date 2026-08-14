package io.prodmind.integration.spring;

import io.opentelemetry.api.trace.Span;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(Span.class)
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
@EnableConfigurationProperties(ProdMindProperties.class)
public class ProdMindAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean
    ProdMindTelemetryFilter prodMindTelemetryFilter(ProdMindProperties properties) {
        return new ProdMindTelemetryFilter(properties.requireProjectId());
    }
}
