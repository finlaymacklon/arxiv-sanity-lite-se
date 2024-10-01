'use strict';

const PaperLite = props => {
    const p = props.paper;
    // provide the correct href depending on what the id is set as
    let url_base = null;
    if (p.id.includes("http://") || p.id.includes("https://")) {
        url_base = '';
    } else if (p.id.includes("/")) {
        url_base = 'https://doi.org/';
    } else {
        url_base = 'http://arxiv.org/abs/';
    };
    return (
    <div class='rel_paper'>
        <div class='rel_title'><a href={url_base + p.id}>{p.title}</a></div>
        <div class='rel_authors'>{p.authors}</div>
        <div class="rel_time">{p.time}</div>
        <div class='rel_abs'>{p.summary}</div>
    </div>
    )
}

ReactDOM.render(<PaperLite paper={paper} />, document.getElementById('wrap'))
