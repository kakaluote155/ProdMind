package io.prodmind.integration.spring;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.regex.Pattern;

@ConfigurationProperties(prefix = "prodmind")
public class ProdMindProperties {
    private static final Pattern PROJECT_ID =
            Pattern.compile("^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$");

    private String projectId;

    public String getProjectId() {
        return projectId;
    }

    public void setProjectId(String projectId) {
        this.projectId = projectId;
    }

    String requireProjectId() {
        if (projectId == null || !PROJECT_ID.matcher(projectId).matches()) {
            throw new IllegalStateException("prodmind.project-id is required and must be valid");
        }
        return projectId;
    }
}
