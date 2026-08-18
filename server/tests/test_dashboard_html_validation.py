from __future__ import annotations

import pytest

from server.utils.dashboard_editing import DashboardValidationError, validate_dashboard_html


def _dashboard(component_body: str) -> str:
    return f"""
    <script type="text/babel">
      const Dashboard = () => {{
        {component_body}
      }};
      ReactDOM.render(React.createElement(Dashboard), document.getElementById('root'));
    </script>
    """


def test_dashboard_validation_accepts_hooks_before_loading_return() -> None:
    validate_dashboard_html(
        _dashboard(
            """
            const [ready, setReady] = React.useState(false);
            const [data, setData] = React.useState([]);
            React.useEffect(() => setReady(true), []);
            if (!ready) return <div>Loading</div>;
            return <div>{data.length}</div>;
            """
        )
    )


def test_dashboard_validation_rejects_hook_after_loading_return() -> None:
    with pytest.raises(DashboardValidationError, match="before the first conditional return"):
        validate_dashboard_html(
            _dashboard(
                """
                const [ready, setReady] = React.useState(false);
                if (!ready) return <div>Loading</div>;
                const [data, setData] = React.useState([]);
                return <div>{data.length}</div>;
                """
            )
        )


def test_dashboard_validation_ignores_nested_component_returns() -> None:
    validate_dashboard_html(
        _dashboard(
            """
            const [data, setData] = React.useState([]);
            const Tooltip = ({ active }) => {
              if (!active) return null;
              return <div>Active</div>;
            };
            return <Tooltip active={data.length > 0} />;
            """
        )
    )


def test_dashboard_validation_ignores_effect_callback_return_before_later_hook() -> None:
    validate_dashboard_html(
        _dashboard(
            """
            const [ready, setReady] = React.useState(false);
            React.useEffect(() => {
              if (!ready) return;
              setReady(true);
            }, [ready]);
            React.useEffect(() => console.log('ready'), [ready]);
            if (!ready) return <div>Loading</div>;
            return <div>Ready</div>;
            """
        )
    )
