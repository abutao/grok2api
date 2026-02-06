class VideoSSE {
    constructor(taskId, handlers = {}) {
        if (!taskId) return null;
        this.eventSource = null;
        this.taskId = taskId;
        this.handlers = handlers;
        this.connect();
    }

    connect() {
        const url = `/v1/video/tasks/${this.taskId}/stream`;
        this.eventSource = new EventSource(url);

        this.eventSource.onmessage = (e) => {
            if (!e.data) return;
            let msg;
            try {
                msg = JSON.parse(e.data);
            } catch {
                return;
            }
            if (this.handlers.onMessage) {
                this.handlers.onMessage(msg);
            }
        };

        this.eventSource.onerror = () => {
            if (this.handlers.onError) {
                this.handlers.onError();
            }
        };

        this.eventSource.onopen = () => {
            if (this.handlers.onOpen) {
                this.handlers.onOpen();
            }
        };
    }

    close() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
    }
}

window.VideoSSE = VideoSSE;
